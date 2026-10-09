export interface ServerErrorInfo {
  status?: number;
  message: string;
  detail?: string;
  url?: string;
}

type Listener = (error: ServerErrorInfo | null) => void;

let currentError: ServerErrorInfo | null = null;
const listeners = new Set<Listener>();

export const serverErrorStore = {
  get: () => currentError,
  set: (error: ServerErrorInfo | null) => {
    currentError = error;
    listeners.forEach((listener) => {
      try {
        listener(currentError);
      } catch (err) {
        console.error("[serverErrorStore] listener error:", err);
      }
    });
  },
  subscribe: (listener: Listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  trigger: (error: ServerErrorInfo) => {
    // Don't overwrite an already displayed modal
    if (!currentError) {
      serverErrorStore.set(error);
    }
  },
  clear: () => {
    serverErrorStore.set(null);
  },
};
