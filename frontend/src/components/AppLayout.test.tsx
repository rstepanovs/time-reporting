import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AppLayout } from "@/components/AppLayout";
import { theme } from "@/theme";

describe("AppLayout", () => {
  it("renders the application title", () => {
    render(
      <MantineProvider theme={theme}>
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </MantineProvider>,
    );

    expect(screen.getByRole("heading", { name: "Time Reporting" })).toBeTruthy();
  });
});
