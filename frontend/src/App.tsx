import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
// The react-dom flavour supports `navigate(..., { flushSync: true })`, which the auth hooks rely on.
import { RouterProvider } from "react-router/dom";

import { queryClient } from "@/api/queryClient";
import { router } from "@/router";
import { theme } from "@/theme";

export function App() {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <DatesProvider settings={{ firstDayOfWeek: 1 }}>
        <Notifications />
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  );
}
