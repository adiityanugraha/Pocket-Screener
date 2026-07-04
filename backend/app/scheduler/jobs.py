"""Job harian scheduler (Day 13).

Tiap job membuka sesi DB sendiri (tidak memakai dependency request) dan, bila
relevan, menghangatkan cache Redis sehingga endpoint melayani hasil instan.
Job didaftarkan ke APScheduler di app.scheduler.scheduler.

Dipakai juga sebagai fungsi biasa (mis. saat testing / pemicuan manual).
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.ai import llm_client
from app.api import ai_analysis as ai_analysis_api
from app.api import benchmark as benchmark_api
from app.api import correlation as correlation_api
from app.api import daily_report as daily_report_api
from app.api import forecast as forecast_api
from app.api import market_summary as market_summary_api
from app.api import monte_carlo as monte_carlo_api
from app.api import stock_report
from app.api import strength as strength_api
from app.api import walkforward as walkforward_api
from app.rag import knowledge_base
from app.api.ranking import CACHE_KEY as RANKING_CACHE_KEY
from app.api.ranking import run_ranking
from app.api.screener import run_screener
from app.cache import redis_client
from app.core import market_data as md
from app.core import strategy_screener
from app.core.instruments import is_index
from app.core.strength_engine import DEFAULT_FULL_POINTS, DEFAULT_TYPE_WEIGHTS
from app.data import fundamentals_derived, fundamentals_fetch
from app.db.models import Stock
from app.db.session import SessionLocal
from app.ml import forecast_model
from app.quant import correlation_matrix as cm
from app.quant import equity_curve as quant_equity
from app.quant import forward_returns as quant_returns
from app.quant import monte_carlo as mc
from app.quant import performance_metrics as pm
from app.quant import walk_forward as wf

log = logging.getLogger("scheduler.jobs")

# Parameter default job (selaras default endpoint).
SCREENER_LIMIT = 10
RANKING_LIMIT = 80
REPORT_USE_ML = True

# Phase 5 - batas & throttle generasi AI (hormati kuota harian Gemini free tier).
AI_ANALYSIS_LIMIT = 15      # AI Analysis hanya untuk top-N saham per malam
AI_THROTTLE_SECONDS = 4.0   # jeda antar pemanggilan LLM (hindari rate limit RPM)


def _tradable_tickers(db) -> list[str]:
    """Daftar ticker saham (indeks dikecualikan) urut alfabetis."""
    tickers = db.scalars(select(Stock.ticker).order_by(Stock.ticker))
    return [t for t in tickers if not is_index(t)]


def job_update_market_data(tickers: list[str] | None = None) -> int:
    """07:00 - Tarik OHLCV terbaru + hitung indikator -> upsert market_data.

    Mengembalikan total bar tersimpan. Cache lama dibiarkan kedaluwarsa via TTL
    (wrapper Redis no-op tidak mendukung wildcard delete).
    """
    with SessionLocal() as db:
        results = md.ingest_universe(db, tickers=tickers)
    total = sum(results.values())
    succeeded = sum(1 for count in results.values() if count > 0)
    log.info("update_market_data: %s/%s ticker OK, %s bar total", succeeded, len(results), total)
    return total


def job_refresh_fundamental_derived() -> int:
    """07:15 (Phase 3) - Refresh metrik fundamental harga-sensitif harian
    (PE/PBV/MarketCap/DividendYield) -> fundamental_derived."""
    with SessionLocal() as db:
        results = fundamentals_derived.refresh_derived(db)
    ok = sum(1 for saved in results.values() if saved)
    log.info("refresh_fundamental_derived: %s/%s ticker ter-refresh", ok, len(results))
    return ok


def job_run_all_strategies(limit: int = SCREENER_LIMIT) -> int:
    """07:30 (Phase 3) - Jalankan SEMUA 9 strategi -> strategy_results.

    Sumber untuk Strategy Matrix (Day 8), Strength Score (Day 9), Explain/Why
    (Day 10). Mengembalikan jumlah baris hasil yang dipersist.
    """
    with SessionLocal() as db:
        result = strategy_screener.screen_all_strategies(db, limit=limit)
    log.info(
        "run_all_strategies: %s baris dipersist (universe %s)",
        result["persisted"],
        result["universe"],
    )
    return result["persisted"]


def job_generate_forecasts(tickers: list[str] | None = None) -> int:
    """16:15 (Phase 3) - Probability Forecast 1D/5D/20D tiap saham -> tabel forecast."""
    generated = 0
    with SessionLocal() as db:
        if tickers is None:
            tickers = _tradable_tickers(db)
        for ticker in tickers:
            if is_index(ticker):
                continue
            result = forecast_model.predict_ticker(db, ticker)
            if result is None:  # bar kurang
                continue
            on_date = forecast_api._latest_date(db, ticker)
            if on_date is not None:
                forecast_api._persist(db, ticker, on_date, result)
                generated += 1
    log.info("generate_forecasts: %s forecast dipersist", generated)
    return generated


def job_generate_strength(tickers: list[str] | None = None) -> int:
    """16:30 (Phase 3) - Strength Score lintas-strategi tiap saham -> strength_score.

    Membaca strategy_results (harus jalan SETELAH job_run_all_strategies 07:30).
    """
    generated = 0
    with SessionLocal() as db:
        if tickers is None:
            tickers = _tradable_tickers(db)
        for ticker in tickers:
            if is_index(ticker):
                continue
            _result, on_date = strength_api.compute_for_ticker(
                db, ticker, dict(DEFAULT_TYPE_WEIGHTS), DEFAULT_FULL_POINTS, persist=True
            )
            if on_date is not None:
                generated += 1
    log.info("generate_strength: %s strength score dipersist", generated)
    return generated


def job_update_fundamentals(tickers: list[str] | None = None) -> int:
    """Mingguan (Phase 3) - Tarik ulang data fundamental dari Yahoo -> fundamentals.

    Fundamental berubah per kuartal; cukup di-refresh mingguan / saat rilis laporan.
    """
    with SessionLocal() as db:
        results = fundamentals_fetch.ingest_fundamentals(db, tickers=tickers)
    ok = sum(1 for count in results.values() if count > 0)
    log.info("update_fundamentals: %s/%s ticker OK", ok, len(results))
    return ok


def job_run_screener(limit: int = SCREENER_LIMIT) -> int:
    """09:30 / 10:00 / 15:30 - Jalankan screener (BSJP+BPJS) -> screening_history.

    run_screener menghitung kedua strategi dan mem-persist semua kandidat yang
    lolos pada bar terbaru (upsert idempoten). Mengembalikan jumlah yang disimpan.
    """
    with SessionLocal() as db:
        result = run_screener(db, limit=limit, use_ml=True)
    log.info("run_screener: %s kandidat dipersist", result["persisted"])
    return result["persisted"]


def job_generate_ranking(limit: int = RANKING_LIMIT, use_ml: bool = True) -> int:
    """16:00 - Hitung Composite Score ranking lalu hangatkan cache Redis."""
    with SessionLocal() as db:
        result = run_ranking(db, limit=limit, use_ml=use_ml)
    cache_key = RANKING_CACHE_KEY.format(limit=limit, ml=use_ml)
    redis_client.cache_set_json(cache_key, result, ttl=redis_client.TTL_RANKING)
    log.info("generate_ranking: %s saham di-rank & di-cache", result["ranked"])
    return result["ranked"]


def job_generate_reports(use_ml: bool = REPORT_USE_ML) -> int:
    """17:00 - Generate AI Stock Report tiap saham lalu hangatkan cache Redis."""
    generated = 0
    with SessionLocal() as db:
        tickers = list(db.scalars(select(Stock.ticker).order_by(Stock.ticker)))
        for ticker in tickers:
            bars = stock_report._load_bars(db, ticker)
            if len(bars) < stock_report.MIN_BARS:
                continue
            payload = stock_report.assemble_report_payload(db, ticker, bars, use_ml)
            cache_key = stock_report.CACHE_KEY.format(ticker=ticker, ml=use_ml)
            redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_REPORT)
            generated += 1
    log.info("generate_reports: %s report dibuat & di-cache", generated)
    return generated


# --------------------------------------------------------------------------- #
# Phase 4 - job malam quant (berat → setelah pasar tutup) + berkala
# --------------------------------------------------------------------------- #
def job_generate_quant_metrics() -> int:
    """18:00 (Phase 4) - Performance Metrics + Benchmark (+IHSG) + Equity Curve.

    get_benchmark me-recompute & mem-persist strategy_performance (5 strategi +
    baris ihsg) lalu menghangatkan cache benchmark; equity_curve.compute_all
    mem-persist tabel equity_curve. Membaca trade log replay_history.
    """
    with SessionLocal() as db:
        benchmark_api.get_benchmark(hold=pm.DEFAULT_HOLD, refresh=True, db=db)
        curves = quant_equity.compute_all(db, persist=True, progress=False)
    log.info("generate_quant_metrics: benchmark + %s equity curve dipersist", len(curves))
    return len(curves)


def job_update_correlation(universe: str = "lq45") -> int:
    """19:00 (Phase 4) - Correlation Matrix universe terbatas -> correlation_matrix + cache."""
    with SessionLocal() as db:
        result = correlation_api.get_correlation(
            universe=universe, window=cm.DEFAULT_WINDOW, refresh=True, db=db
        )
    n = result["n"]
    log.info("update_correlation: %s ticker (%s) korelasi dipersist & di-cache", n, universe)
    return n


def job_run_monte_carlo() -> int:
    """20:00 (Phase 4) - Monte Carlo tiap strategi tervalidasi -> hangatkan cache.

    Tak ada tabel MC; menghangatkan cache Redis = bentuk persistensinya.
    """
    warmed = 0
    with SessionLocal() as db:
        for strategy in pm.VALIDATED_STRATEGIES:
            monte_carlo_api.get_monte_carlo(
                strategy,
                hold=pm.DEFAULT_HOLD,
                horizon_years=mc.DEFAULT_HORIZON_YEARS,
                simulations=mc.DEFAULT_SIMULATIONS,
                refresh=True,
                db=db,
            )
            warmed += 1
    log.info("run_monte_carlo: %s strategi disimulasikan & di-cache", warmed)
    return warmed


def job_refresh_replay_returns(tickers: list[str] | None = None) -> int:
    """Berkala (Phase 4) - Isi/segarkan return forward replay_history.

    Memasukkan kandidat baru (return masih NULL) & mengisi horizon yang sudah
    jatuh tempo (mis. ret_30d setelah 30 hari). Idempoten via upsert.
    """
    with SessionLocal() as db:
        summary = quant_returns.build_replay_history(
            db, tickers=tickers, persist=True, progress=False
        )
    log.info("refresh_replay_returns: %s trade ter-materialisasi", summary["persisted"])
    return summary["persisted"]


def job_refresh_walk_forward() -> int:
    """Berkala (Phase 4) - Refresh walk-forward (paling berat) -> hangatkan cache."""
    warmed = 0
    with SessionLocal() as db:
        for strategy in pm.VALIDATED_STRATEGIES:
            walkforward_api.get_walkforward(
                strategy,
                hold=pm.DEFAULT_HOLD,
                min_train_years=wf.DEFAULT_MIN_TRAIN_YEARS,
                refresh=True,
                db=db,
            )
            warmed += 1
    log.info("refresh_walk_forward: %s strategi di-cache", warmed)
    return warmed


# --------------------------------------------------------------------------- #
# Phase 5 - job malam lapisan AI (SETELAH job quant Phase 4; bergantung outputnya)
# Urutan: KB embeddings -> AI Analysis -> Market Narrator -> Daily Report.
# Semua aman-gagal bila AI nonaktif (di-skip) agar pipeline non-AI tak terganggu.
# --------------------------------------------------------------------------- #
def job_refresh_knowledge_base() -> int:
    """20:30 (Phase 5) - re-embed & index knowledge base ke vector store lokal."""
    if not llm_client.is_available():
        log.info("refresh_knowledge_base: AI nonaktif, dilewati.")
        return 0
    n = knowledge_base.seed()
    log.info("refresh_knowledge_base: %s dokumen di-embed", n)
    return n


def job_generate_ai_analysis(limit: int = AI_ANALYSIS_LIMIT) -> int:
    """21:00 (Phase 5) - AI Analysis untuk top-N saham -> ai_reports + cache.

    Dibatasi top-N (peringkat Composite Score) demi kuota free tier, dan
    di-throttle antar pemanggilan LLM. Mengembalikan jumlah analisis berhasil.
    """
    if not llm_client.is_available():
        log.info("generate_ai_analysis: AI nonaktif, dilewati.")
        return 0
    generated = 0
    with SessionLocal() as db:
        ranking = run_ranking(db, limit=limit, use_ml=True)
        tickers = [item["ticker"] for item in ranking.get("items", [])]
        for index, ticker in enumerate(tickers):
            try:
                result = ai_analysis_api.get_ai_analysis(ticker=ticker, refresh=True, db=db)
                if result.get("ai_generated"):
                    generated += 1
            except Exception as exc:  # noqa: BLE001 - satu saham gagal tak boleh hentikan batch
                log.warning("generate_ai_analysis %s gagal: %s", ticker, exc)
            if index < len(tickers) - 1:
                time.sleep(AI_THROTTLE_SECONDS)
    log.info("generate_ai_analysis: %s/%s analisis dibuat", generated, len(tickers))
    return generated


def job_generate_market_narrative() -> int:
    """21:30 (Phase 5) - Market Narrator -> market_narratives + cache."""
    if not llm_client.is_available():
        log.info("generate_market_narrative: AI nonaktif, dilewati.")
        return 0
    with SessionLocal() as db:
        result = market_summary_api.get_market_summary(refresh=True, db=db)
    log.info("generate_market_narrative: narasi pasar %s dibuat", result.get("date"))
    return 1


def job_generate_daily_report() -> int:
    """22:00 (Phase 5) - AI Daily Report -> cache."""
    if not llm_client.is_available():
        log.info("generate_daily_report: AI nonaktif, dilewati.")
        return 0
    with SessionLocal() as db:
        daily_report_api.get_daily_report(format="json", refresh=True, db=db)
    log.info("generate_daily_report: laporan harian dibuat & di-cache")
    return 1
