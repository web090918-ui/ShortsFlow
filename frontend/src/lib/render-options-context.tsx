"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { DEFAULT_RENDER_OPTIONS, fetchRenderOptions } from "@/lib/render-options";
import type { CaptionTemplate, RenderOptions } from "@/lib/render-options";

const RenderOptionsContext = createContext<RenderOptions>(DEFAULT_RENDER_OPTIONS);
const UserTemplatesContext = createContext<{
  add: (template: CaptionTemplate) => void;
  remove: (id: string) => void;
}>({ add: () => {}, remove: () => {} });

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

  const add = useCallback((template: CaptionTemplate) => {
    setOptions((current) => ({
      ...current,
      user_templates: [...current.user_templates.filter((item) => item.id !== template.id), template],
    }));
  }, []);
  const remove = useCallback((id: string) => {
    setOptions((current) => ({
      ...current,
      user_templates: current.user_templates.filter((item) => item.id !== id),
    }));
  }, []);

  return (
    <RenderOptionsContext.Provider value={options}>
      <UserTemplatesContext.Provider value={{ add, remove }}>{children}</UserTemplatesContext.Provider>
    </RenderOptionsContext.Provider>
  );
}

/** Without a provider (tests, isolated components) the built-in catalog is returned. */
export function useRenderOptions(): RenderOptions {
  return useContext(RenderOptionsContext);
}

/** Add or remove a creator's own template in the loaded catalog. */
export function useUserTemplates() {
  return useContext(UserTemplatesContext);
}
