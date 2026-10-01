"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { DEFAULT_RENDER_OPTIONS, fetchRenderOptions } from "@/lib/render-options";
import type { RenderOptions } from "@/lib/render-options";

const RenderOptionsContext = createContext<RenderOptions>(DEFAULT_RENDER_OPTIONS);

/** Loads the template and layout catalog once per page; pickers read it from context. */
export function RenderOptionsProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<RenderOptions>(DEFAULT_RENDER_OPTIONS);

  useEffect(() => {
    const controller = new AbortController();
    fetchRenderOptions(controller.signal)
      .then(setOptions)
      .catch(() => {
        // The built-in catalog is already shown; a failed refresh changes nothing.
      });
    return () => controller.abort();
  }, []);

  return <RenderOptionsContext.Provider value={options}>{children}</RenderOptionsContext.Provider>;
}

/** Without a provider (tests, isolated components) the built-in catalog is returned. */
export function useRenderOptions(): RenderOptions {
  return useContext(RenderOptionsContext);
}
