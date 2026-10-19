"use client";

import { motion } from "framer-motion";

export interface SimulationProgress {
  completed: number;
  failed: number;
  total: number;
  cacheHits: number;
}

export function ApiLoadingAnimation({ progress }: { progress?: SimulationProgress | null }) {
  const finished = progress ? progress.completed + progress.failed : 0;
  const percent = progress && progress.total > 0 ? (finished / progress.total) * 100 : 0;

  return (
    <div className="fixed inset-0 z-[9999] bg-background/95 backdrop-blur-sm flex items-center justify-center">
      <div className="flex flex-col items-center gap-8">
        {/* Pulsing circles */}
        <div className="relative w-32 h-32">
          {[0, 1, 2].map((index) => (
            <motion.div
              key={index}
              className="absolute inset-0 border-4 border-primary rounded-full"
              initial={{ scale: 0, opacity: 1 }}
              animate={{
                scale: [0, 1.5],
                opacity: [1, 0],
              }}
              transition={{
                duration: 2,
                repeat: Infinity,
                delay: index * 0.6,
                ease: "easeOut",
              }}
            />
          ))}
          <motion.div
            className="absolute inset-0 flex items-center justify-center"
            animate={{
              rotate: 360,
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: "linear",
            }}
          >
            <svg
              width="64"
              height="64"
              viewBox="0 0 48 48"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <motion.path
                d="M24 4L26.472 17.528L36.728 11.272L30.472 21.528L44 24L30.472 26.472L36.728 36.728L26.472 30.472L24 44L21.528 30.472L11.272 36.728L17.528 26.472L4 24L17.528 21.528L11.272 11.272L21.528 17.528L24 4Z"
                fill="url(#gradient-api)"
                animate={{
                  opacity: [0.6, 1, 0.6],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
              <defs>
                <linearGradient id="gradient-api" x1="4" y1="4" x2="44" y2="44">
                  <stop offset="0%" stopColor="#4285f4" />
                  <stop offset="33%" stopColor="#9b72cb" />
                  <stop offset="66%" stopColor="#d96570" />
                  <stop offset="100%" stopColor="#f2a746" />
                </linearGradient>
              </defs>
            </svg>
          </motion.div>
        </div>

        {/* Loading text with animated dots */}
        <div className="text-center space-y-3">
          <motion.h2
            className="text-2xl font-bold text-foreground"
            animate={{
              opacity: [0.5, 1, 0.5],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          >
            Generating Scenario
          </motion.h2>
          <div className="flex items-center justify-center gap-2">
            <span className="text-sm text-muted-foreground">
              {progress
                ? `${finished}/${progress.total} personas responded` +
                  (progress.cacheHits > 0 ? ` (${progress.cacheHits} from cache)` : "")
                : "Connecting to ADK backend"}
            </span>
            {[0, 1, 2].map((index) => (
              <motion.span
                key={index}
                className="w-1.5 h-1.5 bg-primary rounded-full"
                animate={{
                  y: [0, -8, 0],
                }}
                transition={{
                  duration: 0.6,
                  repeat: Infinity,
                  delay: index * 0.15,
                  ease: "easeInOut",
                }}
              />
            ))}
          </div>
          <p className="text-xs text-muted-foreground max-w-md">
            This may take a few moments as we process your scenario...
          </p>
        </div>

        {/* Progress bar */}
        <div className="w-96 max-w-[calc(100vw-2rem)] h-2 bg-muted rounded-full overflow-hidden">
          {progress ? (
            <motion.div
              className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500"
              initial={false}
              animate={{ width: `${percent}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          ) : (
            <motion.div
              className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500"
              animate={{
                x: ["-100%", "200%"],
              }}
              transition={{
                duration: 2,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
