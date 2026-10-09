"use client";

import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { serverErrorStore, ServerErrorInfo } from "@/lib/server-error";
import { AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

export function ServerErrorDialog() {
  const [error, setError] = useState<ServerErrorInfo | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    // Sync initial state
    setError(serverErrorStore.get());
    return serverErrorStore.subscribe((err) => {
      setError(err);
      setShowDetails(false);
    });
  }, []);

  if (!error) return null;

  const handleClose = () => {
    serverErrorStore.clear();
  };

  const handleRefresh = () => {
    window.location.reload();
  };

  return (
    <Dialog
      open={Boolean(error)}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent className="sm:max-w-md p-6 gap-4">
        <DialogHeader className="gap-3">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-foreground">
                We ran into a problem
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {error.status ? `Server response ${error.status}` : "Connection issue"}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3 py-1 text-sm text-foreground/90">
          <p>
            We encountered a problem communicating with the server. Please visit after some time, or try refreshing the page.
          </p>

          {error.detail && (
            <div className="rounded-lg border border-border/70 bg-muted/50 p-2.5 text-xs text-muted-foreground">
              <button
                type="button"
                onClick={() => setShowDetails(!showDetails)}
                className="flex w-full items-center justify-between font-mono text-[11px] font-medium hover:text-foreground cursor-pointer transition-colors"
              >
                <span>Technical details</span>
                {showDetails ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>
              {showDetails && (
                <div className="mt-2 pt-2 border-t border-border/50 font-mono text-[11px] break-words text-destructive dark:text-destructive-foreground">
                  {error.url && (
                    <div className="mb-1 text-muted-foreground">Endpoint: {error.url}</div>
                  )}
                  <div>{error.detail}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:justify-end">
          <Button variant="outline" size="sm" onClick={handleClose}>
            Dismiss
          </Button>
          <Button size="sm" onClick={handleRefresh} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Refresh page</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
