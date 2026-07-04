"use client";

// Error boundary level-route (Next App Router). Menangkap error render yang tak
// tertangani agar halaman tidak blank - menampilkan kartu Vestigo + tombol coba lagi.

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log ke console; ganti dengan layanan error-tracking (mis. Sentry) bila ada.
    console.error(error);
  }, [error]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div className="card" style={{ maxWidth: 480, textAlign: "center" }}>
        <h1 className="card-title">Terjadi kesalahan</h1>
        <p className="card-sub" style={{ marginTop: 0 }}>
          Sesuatu tak berjalan semestinya saat memuat halaman.
        </p>
        {error.digest && <p className="t3 small mono">Ref: {error.digest}</p>}
        <div>
          <button className="primary-btn" onClick={reset}>
            Coba lagi
          </button>
        </div>
      </div>
    </main>
  );
}
