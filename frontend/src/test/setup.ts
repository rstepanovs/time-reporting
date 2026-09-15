import { notifications } from "@mantine/notifications";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The notifications queue is a module-level store outside the React tree, so a toast shown in
  // one test (e.g. via `notifications.show`) would otherwise still be queued for the next test's
  // freshly mounted <Notifications />.
  notifications.clean();
  notifications.cleanQueue();
});

// Mantine relies on browser APIs that jsdom does not implement.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

window.ResizeObserver = ResizeObserverStub;

// Mantine's Select/Combobox scrolls the active option into view as the keyboard cursor moves;
// jsdom has no layout engine, so this is a no-op here rather than an unimplemented-method throw.
Element.prototype.scrollIntoView = () => {};

// Mantine's autosizing Textarea listens for font-loading to re-measure; jsdom has no FontFaceSet.
if (!document.fonts) {
  Object.defineProperty(document, "fonts", {
    writable: true,
    value: {
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  });
}
