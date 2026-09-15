import { Button, Group, Stack, Text, Title } from "@mantine/core";
import { useSearchParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { MonthCalendar } from "@/timesheets/MonthCalendar";
import { addMonths, formatMonthLabel, todayIso } from "@/timesheets/week";
import { YearHoursTable } from "@/timesheets/YearHoursTable";

const MONTH_PARAM_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function currentYearMonth(): { year: number; month: number } {
  const today = todayIso();
  return { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) };
}

function formatMonthParam(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function HoursPage() {
  const user = useAuthenticatedUser();
  const [searchParams, setSearchParams] = useSearchParams();

  const monthParam = searchParams.get("month");
  const { year, month } =
    monthParam && MONTH_PARAM_PATTERN.test(monthParam)
      ? { year: Number(monthParam.slice(0, 4)), month: Number(monthParam.slice(5, 7)) }
      : currentYearMonth();

  function navigateToMonth(nextYear: number, nextMonth: number) {
    const params = new URLSearchParams(searchParams);
    params.set("month", formatMonthParam(nextYear, nextMonth));
    setSearchParams(params);
  }

  const today = todayIso();
  const thisMonth = currentYearMonth();

  return (
    <Stack>
      <Title order={2}>My hours</Title>

      <Group>
        <Button
          variant="default"
          onClick={() => {
            const { year: y, month: m } = addMonths(year, month, -1);
            navigateToMonth(y, m);
          }}
        >
          ← Previous
        </Button>
        <Button
          variant="default"
          onClick={() => navigateToMonth(thisMonth.year, thisMonth.month)}
        >
          This month
        </Button>
        <Button
          variant="default"
          onClick={() => {
            const { year: y, month: m } = addMonths(year, month, 1);
            navigateToMonth(y, m);
          }}
        >
          Next →
        </Button>
        <Text fw={500}>{formatMonthLabel(year, month)}</Text>
      </Group>

      <MonthCalendar userId={user.id} year={year} month={month} today={today} />
      <YearHoursTable userId={user.id} year={year} />
    </Stack>
  );
}
