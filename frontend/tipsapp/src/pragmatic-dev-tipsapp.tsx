import React from "react";
import ReactDOMClient from "react-dom/client";
import singleSpaReact from "single-spa-react";

import { TipsPanel } from "./TipsPanel";
import tailwindSheet from "./styles/tailwind.css";

/**
 * Resolve the DOM element to render into — but INSIDE a Shadow DOM so this
 * MFE's Tailwind can't leak in/out (it renders side-by-side with queryapp).
 *
 * - Attach a shadow root to the container single-spa-layout created.
 * - Inject the compiled Tailwind as a constructable stylesheet *inside* the
 *   shadow root (global <head> styles don't pierce the boundary).
 * - Render React into a div within the shadow root.
 *
 * CSS custom properties (e.g. --brand) still pierce the boundary, so shared
 * theme tokens from the shell continue to work.
 */
function shadowDomElementGetter(props: { name: string }): HTMLElement {
  const containerId = `single-spa-application:${props.name}`;
  let container = document.getElementById(containerId);
  if (!container) {
    container = document.createElement("div");
    container.id = containerId;
    document.body.appendChild(container);
  }

  const shadow = container.shadowRoot ?? container.attachShadow({ mode: "open" });
  if (shadow.adoptedStyleSheets.length === 0) {
    shadow.adoptedStyleSheets = [tailwindSheet];
  }

  // The shadow host must fill its layout slot so the inner `h-full` flex chain
  // resolves and the tips list (overflow-y-auto) becomes the scroll region —
  // otherwise the list can't scroll and its content is clipped by the layout.
  container.style.height = "100%";
  container.style.minHeight = "0";

  let mountEl = shadow.querySelector<HTMLElement>("#tips-root");
  if (!mountEl) {
    mountEl = document.createElement("div");
    mountEl.id = "tips-root";
    mountEl.style.height = "100%";
    shadow.appendChild(mountEl);
  }
  return mountEl;
}

const lifecycles = singleSpaReact({
  React,
  ReactDOMClient,
  rootComponent: TipsPanel,
  domElementGetter: shadowDomElementGetter as unknown as () => HTMLElement,
  errorBoundary() {
    return (
      <div style={{ padding: 16, color: "#b91c1c", fontSize: 14 }}>
        Tips panel failed to load.
      </div>
    );
  },
});

export const { bootstrap, mount, unmount } = lifecycles;

