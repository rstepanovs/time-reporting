import { Alert, Loader } from "@mantine/core";

import { useYearHours } from "@/timesheets/hooks";
import { YearHoursTableView } from "@/timesheets/YearHoursTableView";

type Props = {
  userId: string;
  year: number;
  title?: string;
};

/** Loads and renders one user's year of hours. Reusable wherever a year table is needed (the
 * `/hours` page, a manager's view of an employee's year, ...) — see `YearHoursTableView` for the
 * presentational half if the data is already at hand. */
export function YearHoursTable({ userId, year, title }: Props) {
  const query = useYearHours(userId, year);

  if (query.isPending) return <Loader />;
  if (query.isError || !query.data) {
    return <Alert color="red">Could not load this year's hours.</Alert>;
  }

  return <YearHoursTableView data={query.data} title={title} />;
}
