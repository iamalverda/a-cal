"use client";

/**
 * Voice input hook — wraps the Web Speech API for speech-to-text.
 *
 * Charter §6 (Q6): voice is one of three interaction modes (chat + voice +
 * command bar), with voice as the default. This hook provides browser-based
 * speech recognition so users can talk to the conductor instead of typing.
 *
 * The Web Speech API is available in Chromium-based browsers and Safari.
 * When unavailable, `supported` is false and `startListening` is a no-op.
 */

import { useState, useRef, useCallback, useEffect } from "react";

// --- Web Speech API type declarations (not in standard TS DOM lib) ---------

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

interface SpeechRecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message: string;
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

interface SpeechRecognitionStatic {
  new (): SpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionStatic;
    webkitSpeechRecognition?: SpeechRecognitionStatic;
  }
}

// --- Hook ------------------------------------------------------------------

export interface VoiceInputState {
  /** Whether the browser supports speech recognition. */
  supported: boolean;
  /** Whether we are currently listening to the microphone. */
  listening: boolean;
  /** The final transcript accumulated so far. */
  transcript: string;
  /** Interim (non-final) transcript — what's being heard right now. */
  interimTranscript: string;
  /** Error message if recognition failed (cleared on next start). */
  error: string | null;
}

export interface UseVoiceInputOptions {
  /** Called with the final transcript when listening stops. */
  onTranscript?: (text: string) => void;
  /** Language code (BCP-47). Defaults to en-US. */
  lang?: string;
  /** Whether to keep listening continuously (restarts on end). */
  continuous?: boolean;
}

export function useVoiceInput(options: UseVoiceInputOptions = {}): {
  state: VoiceInputState;
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
} {
  const { onTranscript, lang = "en-US", continuous = false } = options;
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  const shouldRestartRef = useRef(false);

  // Keep the callback ref current without recreating the recognition object.
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  // Detect browser support.
  const SR = typeof window !== "undefined"
    ? (window.SpeechRecognition || window.webkitSpeechRecognition)
    : undefined;
  const supported = !!SR;

  // Create the recognition instance lazily.
  const getRecognition = useCallback((): SpeechRecognition | null => {
    if (!SR) return null;
    if (recognitionRef.current) return recognitionRef.current;

    const rec = new SR();
    rec.lang = lang;
    rec.continuous = continuous;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      setListening(true);
      setError(null);
    };

    rec.onresult = (event: SpeechRecognitionEvent) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const alt = result[0];
        if (result.isFinal) {
          finalText += alt.transcript;
        } else {
          interimText += alt.transcript;
        }
      }
      if (finalText) {
        setTranscript((prev) => (prev + " " + finalText).trim());
      }
      setInterimTranscript(interimText);
    };

    rec.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === "no-speech" || event.error === "aborted") return;
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setError("Microphone access denied. Check browser permissions.");
      } else {
        setError(`Voice input error: ${event.error}`);
      }
      setListening(false);
      shouldRestartRef.current = false;
    };

    rec.onend = () => {
      setListening(false);
      setInterimTranscript("");
      // Auto-restart if in continuous mode and not manually stopped.
      if (shouldRestartRef.current) {
        try {
          rec.start();
        } catch {
          shouldRestartRef.current = false;
        }
      } else {
        // Fire the callback with the accumulated transcript.
        setTranscript((finalText) => {
          if (finalText && onTranscriptRef.current) {
            onTranscriptRef.current(finalText);
          }
          return finalText;
        });
      }
    };

    recognitionRef.current = rec;
    return rec;
  }, [SR, lang, continuous]);

  const startListening = useCallback(() => {
    const rec = getRecognition();
    if (!rec) return;
    setTranscript("");
    setInterimTranscript("");
    setError(null);
    shouldRestartRef.current = continuous;
    try {
      rec.start();
    } catch {
      // start() throws if already started — safe to ignore.
    }
  }, [getRecognition, continuous]);

  const stopListening = useCallback(() => {
    shouldRestartRef.current = false;
    const rec = recognitionRef.current;
    if (rec) {
      try {
        rec.stop();
      } catch {
        // stop() throws if not started — safe to ignore.
      }
    }
    setListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      shouldRestartRef.current = false;
      const rec = recognitionRef.current;
      if (rec) {
        try {
          rec.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  return {
    state: { supported, listening, transcript, interimTranscript, error },
    startListening,
    stopListening,
    resetTranscript,
  };
}
