import { Anchor, Group, Paper, Stack, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { Link } from "react-router";

type Props = {
  title: string;
  children: ReactNode;
  /** A link shown bottom-right, e.g. "Details →" to a fuller view of the same data. */
  footer?: { label: string; to: string };
  /** Tints the card to call it out as "this one" among its siblings (e.g. the current month). */
  highlighted?: boolean;
};

/** The common frame every dashboard widget card renders inside: a title, its content, and an
 * optional link to a fuller view. */
export function DashboardCard({ title, children, footer, highlighted }: Props) {
  return (
    <Paper
      withBorder
      p="md"
      radius="md"
      h="100%"
      bg={highlighted ? "var(--mantine-primary-color-light)" : undefined}
      style={
        highlighted ? { borderColor: "var(--mantine-primary-color-filled)" } : undefined
      }
    >
      <Stack gap="sm" h="100%" justify="space-between">
        <Stack gap="sm">
          <Title order={4}>{title}</Title>
          {children}
        </Stack>
        {footer && (
          <Group justify="flex-end">
            <Anchor component={Link} to={footer.to} size="sm">
              {footer.label}
            </Anchor>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
