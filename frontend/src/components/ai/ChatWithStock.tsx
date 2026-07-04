"use client";

// Chat With Stock (Phase 5) - tanya-jawab streaming berbasis data sistem.
// session_id digenerate klien; streaming via streamChat().

import { useRef, useState } from "react";
import { streamChat } from "@/lib/api";
import { VCard } from "../vestigo/Card";
import { VestigoLogo } from "../VestigoLogo";

type Msg = { role: "user" | "assistant"; text: string };

export function ChatWithStock() {
  const sessionId = useRef<string>(
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : String(Date.now()),
  );
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "" }]);
    try {
      await streamChat(text, sessionId.current, (chunk) => {
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = {
            role: "assistant",
            text: next[next.length - 1].text + chunk,
          };
          return next;
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal mengirim pesan");
      setMessages((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
    }
  }

  return (
    <VCard
      title="Chat With Stock"
      sub="Tanya apa saja soal saham IDX"
      subMono={false}
      className="chat-card"
    >
      {messages.length === 0 ? (
        <div className="chat-empty">
          <VestigoLogo size={84} className="chat-owl" />
          <p className="chat-empty-title">Mulai percakapan dengan Vesto</p>
          <p className="chat-empty-sub">
            Belum ada percakapan. Coba, mis. &ldquo;Kenapa BBCA score tinggi?&rdquo; atau
            &ldquo;Apakah BMRI overbought?&rdquo;
          </p>
        </div>
      ) : (
        <div className="chat-log" style={{ maxHeight: 384, overflowY: "auto" }}>
          {messages.map((m, i) => (
            <div
              key={i}
              className="chat-turn"
              style={
                m.role === "user"
                  ? { background: "var(--accent-tint)", border: "1px solid rgba(193,154,107,0.28)" }
                  : undefined
              }
            >
              <p className={m.role === "user" ? "chat-q" : "chat-a"}>
                {m.text || (busy ? "…" : "")}
              </p>
            </div>
          ))}
        </div>
      )}

      {error && <p className="small num-down">{error}</p>}

      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          placeholder="Tulis pertanyaan…"
          className="field-input"
        />
        <button type="submit" disabled={busy || !input.trim()} className="primary-btn">
          {busy ? "…" : "Kirim"}
        </button>
      </form>
    </VCard>
  );
}
