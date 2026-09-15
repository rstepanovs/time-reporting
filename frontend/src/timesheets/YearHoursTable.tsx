import { Alert, Badge, Loader, Stack, Table, Text, Title, UnstyledButton } from "@mantine/core";
import { useState } from "react";

import type { MonthHours } from "@/timesheets/api";
import { useYearHours } from "@/timesheets/hooks";
import { formatHours } from "@/timesheets/week";

const MONTH_LABELS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** The month's hours against what was expected of it "to date" — already equal to the full
 * month's expected hours for a past month, so this single field works for every row. */
function formatDelta(totalHours: string, expectedHoursToDate: string): { text: string; color?: string } {
  const diff = Math.round((Number(totalHours) - Number(expectedHoursToDate)) * 100) / 100;
  if (diff === 0) return { text: "0" };
  return { text: `${diff > 0 ? "+" : ""}${formatHours(diff.toFixed(2))}`, color: diff > 0 ? "green" : "red" };
}

type Props = {
  userId: string;
  year: number;
};

export function YearHoursTable({ userId, year }: Props) {
  const query = useYearHours(userId, year);
  const [expandedMonths, setExpandedMonths] = useState<ReadonlySet<number>>(new Set());

  if (query.isPending) return <Loader />;
  if (query.isError || !query.data) {
    return <Alert color="red">Could not load this year's hours.</Alert>;
  }

  const data = query.data;
  const showOther = data.months.some((month) => Number(month.totals.other_hours) > 0);

  function toggleMonth(month: number) {
    setExpandedMonths((previous) => {
      const next = new Set(previous);
      if (next.has(month)) next.delete(month);
      else next.add(month);
      return next;
    });
  }

  return (
    <Stack gap="xs">
      <Title order={3}>{year}</Title>
      {data.months.length === 0 ? (
        <Text c="dimmed">No hours booked this year yet.</Text>
      ) : (
        <Table.ScrollContainer minWidth={720}>
          <Table withTableBorder withColumnBorders striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Month</Table.Th>
                <Table.Th>Expected</Table.Th>
                <Table.Th>Normal</Table.Th>
                <Table.Th>Overtime</Table.Th>
                <Table.Th>Travel</Table.Th>
                {showOther && <Table.Th>Other</Table.Th>}
                <Table.Th>Total</Table.Th>
                <Table.Th>Δ</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.months.map((month) => (
                <MonthRows
                  key={month.month}
                  month={month}
                  showOther={showOther}
                  expanded={expandedMonths.has(month.month)}
                  onToggle={() => toggleMonth(month.month)}
                />
              ))}
            </Table.Tbody>
            <Table.Tfoot>
              <Table.Tr>
                <Table.Th>Total {year}</Table.Th>
                <Table.Th>{formatHours(data.expected_hours)}</Table.Th>
                <Table.Th>{formatHours(data.totals.normal_hours)}</Table.Th>
                <Table.Th>{formatHours(data.totals.overtime_hours)}</Table.Th>
                <Table.Th>{formatHours(data.totals.travel_hours)}</Table.Th>
                {showOther && <Table.Th>{formatHours(data.totals.other_hours)}</Table.Th>}
                <Table.Th>{formatHours(data.totals.total_hours)}</Table.Th>
                <YearDelta totalHours={data.totals.total_hours} expected={data.expected_hours_to_date} />
              </Table.Tr>
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}

function YearDelta({ totalHours, expected }: { totalHours: string; expected: string }) {
  const delta = formatDelta(totalHours, expected);
  return <Table.Th c={delta.color}>{delta.text}</Table.Th>;
}

function MonthRows({
  month,
  showOther,
  expanded,
  onToggle,
}: {
  month: MonthHours;
  showOther: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const delta = formatDelta(month.totals.total_hours, month.expected_hours_to_date);
  const hasProjects = month.projects.length > 0;

  return (
    <>
      <Table.Tr data-current={month.is_current || undefined}>
        <Table.Td>
          <UnstyledButton
            onClick={hasProjects ? onToggle : undefined}
            disabled={!hasProjects}
            aria-expanded={hasProjects ? expanded : undefined}
            aria-label={`${expanded ? "Collapse" : "Expand"} ${MONTH_LABELS[month.month - 1]}`}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Text component="span" size="xs" style={{ visibility: hasProjects ? "visible" : "hidden" }}>
              {expanded ? "▾" : "▸"}
            </Text>
            <Text component="span" fw={month.is_current ? 600 : undefined}>
              {MONTH_LABELS[month.month - 1]}
            </Text>
            {month.is_current && (
              <Badge size="xs" variant="light">
                In progress
              </Badge>
            )}
          </UnstyledButton>
        </Table.Td>
        <Table.Td>{formatHours(month.expected_hours)}</Table.Td>
        <Table.Td>{formatHours(month.totals.normal_hours)}</Table.Td>
        <Table.Td>{formatHours(month.totals.overtime_hours)}</Table.Td>
        <Table.Td>{formatHours(month.totals.travel_hours)}</Table.Td>
        {showOther && <Table.Td>{formatHours(month.totals.other_hours)}</Table.Td>}
        <Table.Td>{formatHours(month.totals.total_hours)}</Table.Td>
        <Table.Td c={delta.color}>{delta.text}</Table.Td>
      </Table.Tr>
      {expanded &&
        month.projects.map((project) => (
          <Table.Tr key={project.project.id} data-role="project-row">
            <Table.Td pl="xl">
              <Text size="sm" c="dimmed">
                {project.project.customer.name} · {project.project.name}
              </Text>
            </Table.Td>
            <Table.Td />
            <Table.Td>{formatHours(project.totals.normal_hours)}</Table.Td>
            <Table.Td>{formatHours(project.totals.overtime_hours)}</Table.Td>
            <Table.Td>{formatHours(project.totals.travel_hours)}</Table.Td>
            {showOther && <Table.Td>{formatHours(project.totals.other_hours)}</Table.Td>}
            <Table.Td>{formatHours(project.totals.total_hours)}</Table.Td>
            <Table.Td />
          </Table.Tr>
        ))}
    </>
  );
}
