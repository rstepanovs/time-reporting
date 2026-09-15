import { Anchor, Badge, Group, Table, Text, Tooltip } from "@mantine/core";
import { Link } from "react-router";

import type { TeamMemberWarning, TeamProject, TimesheetWeekStatus } from "@/timesheets/api";
import { addDays, formatHours } from "@/timesheets/week";

type Props = {
  project: TeamProject;
  /** Every week column shared across a month's projects (from `TeamMonthOverview.weeks`). */
  weekStarts: string[];
  year: number;
  month: number;
};

const STATUS_COLOR: Record<TimesheetWeekStatus, string> = {
  draft: "gray",
  submitted: "yellow",
  approved: "green",
  returned: "red",
};
const STATUS_LABEL: Record<TimesheetWeekStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  returned: "Returned",
};

const WARNING_LABEL: Record<NonNullable<TeamMemberWarning>, string> = {
  no_entries: "No time booked on this project this month",
  under_expected_hours: "Reported hours are below what's expected so far this month",
};

/** "07.09" from an ISO date, for a compact week-column header. */
function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** A week straddles the queried month when part of it (its start or its end) falls outside that
 * month — its own status still governs the whole week (see the implementation plan), but the
 * column is marked so a manager isn't surprised by hours outside the header's month. */
function isStraddling(weekStart: string, year: number, month: number): boolean {
  const monthKey = `${year}-${String(month).padStart(2, "0")}`;
  const weekEnd = addDays(weekStart, 6);
  return weekStart.slice(0, 7) !== monthKey || weekEnd.slice(0, 7) !== monthKey;
}

/** One managed project's members against the month's ISO weeks: each cell is that member's
 * status and project hours for the week, linking to their timesheet. */
export function TeamWeekMatrix({ project, weekStarts, year, month }: Props) {
  return (
    <Table.ScrollContainer minWidth={480}>
      <Table withTableBorder withColumnBorders striped>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Member</Table.Th>
            {weekStarts.map((weekStart) => (
              <Table.Th key={weekStart}>
                {shortDate(weekStart)}
                {isStraddling(weekStart, year, month) && (
                  <Text span c="dimmed">
                    {" "}
                    *
                  </Text>
                )}
              </Table.Th>
            ))}
            <Table.Th>Month hours</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {project.members.map((member) => (
            <Table.Tr key={member.user.id}>
              <Table.Td>
                <Group gap={4} wrap="nowrap">
                  <Text size="sm">{member.user.name}</Text>
                  {!member.is_member && (
                    <Badge size="xs" color="gray" variant="light">
                      Removed
                    </Badge>
                  )}
                  {member.warning && (
                    <Tooltip label={WARNING_LABEL[member.warning]}>
                      <Text size="sm">⚠️</Text>
                    </Tooltip>
                  )}
                </Group>
              </Table.Td>
              {weekStarts.map((weekStart) => {
                const week = member.weeks.find((entry) => entry.week_start === weekStart);
                if (!week) return <Table.Td key={weekStart} />;
                return (
                  <Table.Td key={weekStart}>
                    <Anchor
                      component={Link}
                      to={`/timesheet?week=${weekStart}&user=${member.user.id}`}
                      size="sm"
                      underline="never"
                    >
                      <Badge size="xs" color={STATUS_COLOR[week.status]} variant="light">
                        {STATUS_LABEL[week.status]}
                      </Badge>
                      <Text size="xs">{formatHours(week.project_hours)} h</Text>
                    </Anchor>
                  </Table.Td>
                );
              })}
              <Table.Td>{formatHours(member.project_hours)} h</Table.Td>
            </Table.Tr>
          ))}
          {project.members.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={weekStarts.length + 2}>
                <Text size="sm" c="dimmed">
                  No one has booked time on this project this month.
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
