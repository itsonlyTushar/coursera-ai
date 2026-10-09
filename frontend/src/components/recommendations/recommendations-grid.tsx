"use client";

import React from "react";
import { Recommendation } from "@/types";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { RecommendationCard } from "./recommendation-card";

interface RecommendationsGridProps {
  recommendations: Recommendation[];
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
  searchQuery?: string;
  onSelectRecommendation: (item: Recommendation) => void;
}

export function RecommendationsGrid({
  recommendations,
  isLoading,
  isError = false,
  onRetry,
  searchQuery = "",
  onSelectRecommendation,
}: RecommendationsGridProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-sm text-muted-foreground">
        <Spinner className="h-4 w-4 text-muted-foreground" />
        <span>Loading curated recommendations...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-center border border-dashed border-border/80 rounded-xl bg-card/40 p-8">
        <div className="h-10 w-10 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">
            Unable to load recommendations
          </p>
          <p className="text-xs text-muted-foreground max-w-sm">
            We ran into a problem connecting to the server. Please visit after some time.
          </p>
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
            Try again
          </Button>
        )}
      </div>
    );
  }

  if (recommendations.length === 0) {
    return (
      <div className="text-center py-16 text-sm text-muted-foreground">
        {searchQuery
          ? "No recommendations match your search."
          : "No curated recommendations yet. Use the chat to generate insights and add them here."}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {recommendations.map((item) => (
        <RecommendationCard
          key={item.id}
          item={item}
          onSelect={onSelectRecommendation}
        />
      ))}
    </div>
  );
}
