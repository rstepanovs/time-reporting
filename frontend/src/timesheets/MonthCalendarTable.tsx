import { Anchor, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { Link } from "react-router";

import type { CalendarDayHours, CalendarWeekHours, MonthCalendar } from "@/timesheets/api";
import { dayKind, dayKindBackground } from "@/timesheets/dayKind";
import { dayStatus, type DayStatus } from "@/timesheets/dayStatus";
import { formatHours, formatMonthLabel } from "@/timesheets/week";

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Only statuses with hours booked get a color here; "missing" instead reddens the day number
// (see DayCell) since there's no hours text to color, and "today" gets an outline instead of a
// text color so it isn't lost for a colorblind viewer.
const HOURS_COLOR: Partial<Record<DayStatus, string>> = {
  complete: "green",
  partial: "orange",
  extra: "blue",
};

type Props = {
  calendar: MonthCalendar;
  today: string;
  /** Overrides the default "<Month> <Year>" heading; pass "" to render no heading at all. */
  title?: string;
};

/** Presentational: renders an already-loaded month calendar. See `MonthCalendar` for the
 * data-loading wrapper most callers want. */
export function MonthCalendarTable({ calendar, today, title }: Props) {
  return (
    <Stack gap="xs">
      {title !== "" && (
        <Title order={3}>{title ?? formatMonthLabel(calendar.year, calendar.month)}</Title>
      )}
      <Table.ScrollContainer minWidth={640}>
        <Table withTableBorder withColumnBorders striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Week</Table.Th>
              {WEEKDAY_LABELS.map((label) => (
                <Table.Th key={label}>{label}</Table.Th>
              ))}
              <Table.Th>Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {calendar.weeks.map((week) => (
              <WeekRow key={week.week_start} week={week} today={today} />
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="sm" c="dimmed">
        {formatHours(calendar.hours)} h booked · {formatHours(calendar.expected_hours_to_date)} h
        expected to date · {formatHours(calendar.expected_hours)} h expected this month
      </Text>
    </Stack>
  );
}

function WeekRow({ week, today }: { week: CalendarWeekHours; today: string }) {
  return (
    <Table.Tr>
      <Table.Td>
        <Anchor component={Link} to={`/timesheet?week=${week.week_start}`} size="sm">
          {week.iso_week}
        </Anchor>
      </Table.Td>
      {week.days.map((day) => (
        <DayCell key={day.calendar_day.day} day={day} today={today} />
      ))}
      <Table.Td>
        {formatHours(week.hours)} / {formatHours(week.expected_hours)} h
      </Table.Td>
    </Table.Tr>
  );
}

function DayCell({ day, today }: { day: CalendarDayHours; today: string }) {
  const kind = dayKind(day.calendar_day);
  const background = dayKindBackground(kind);
  const status = dayStatus(day, today);
  const dayNumber = Number(day.calendar_day.day.slice(-2));
  const dayNumberColor = !day.in_month ? "dimmed" : status === "missing" ? "red" : undefined;

  const cell = (
    <Table.Td
      data-kind={kind}
      data-status={status}
      style={{
        backgroundColor: background,
        outline: status === "today" ? "2px solid var(--mantine-color-blue-6)" : undefined,
        outlineOffset: -2,
      }}
    >
      <Text size="xs" c={dayNumberColor} fw={status === "today" ? 700 : undefined}>
        {dayNumber}
      </Text>
      {Number(day.hours) > 0 && (
        <Text size="xs" c={HOURS_COLOR[status]} fw={500}>
          {formatHours(day.hours)}
        </Text>
      )}
    </Table.Td>
  );

  if (day.calendar_day.non_working_day) {
    return <Tooltip label={day.calendar_day.non_working_day.name}>{cell}</Tooltip>;
  }
  return cell;
}
