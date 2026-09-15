import { Alert, Loader } from "@mantine/core";

import { useMonthCalendar } from "@/timesheets/hooks";
import { MonthCalendarTable } from "@/timesheets/MonthCalendarTable";

type Props = {
  userId: string;
  year: number;
  month: number;
  today: string;
  title?: string;
};

/** Loads and renders one user's month calendar. Reusable wherever a month calendar is needed
 * (the `/hours` page, a manager's view of a worker's month, ...) — see `MonthCalendarTable` for
 * the presentational half if the data is already at hand. */
export function MonthCalendar({ userId, year, month, today, title }: Props) {
  const query = useMonthCalendar(userId, year, month);

  if (query.isPending) return <Loader />;
  if (query.isError || !query.data) {
    return <Alert color="red">Could not load the month calendar.</Alert>;
  }

  return <MonthCalendarTable calendar={query.data} today={today} title={title} />;
}
