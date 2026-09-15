import { Alert, Loader } from "@mantine/core";
import { CompositeChart } from "@mantine/charts";

import { DashboardCard } from "@/components/DashboardCard";
import { useWeeklyHours } from "@/timesheets/hooks";
import { formatIsoWeekLabel } from "@/timesheets/week";

const WEEKS_SHOWN = 6;
const BOOKED_SERIES = "Hours booked";
const EXPECTED_SERIES = "Expected hours";

type Props = {
  userId: string;
};

function formatHoursValue(value: number): string {
  return `${value} h`;
}

/** Hours booked per week (bars) against expected hours (a reference line), both on the same hours
 * axis — never a fill-rate percentage on a second axis, so the two stay directly comparable.
 * `userId` selects whose weeks to load. */
export function WeeklyHoursChart({ userId }: Props) {
  const query = useWeeklyHours(userId, WEEKS_SHOWN);

  if (query.isPending) {
    return (
      <DashboardCard title="Hours per week">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="Hours per week">
        <Alert color="red">Could not load weekly hours.</Alert>
      </DashboardCard>
    );
  }

  const data = query.data.weeks.map((week) => ({
    label: week.is_current ? "Current" : formatIsoWeekLabel(week.iso_week),
    [BOOKED_SERIES]: Number(week.totals.total_hours),
    [EXPECTED_SERIES]: Number(week.expected_hours),
  }));

  return (
    <DashboardCard title="Hours per week" footer={{ label: "My hours →", to: "/hours" }}>
      <CompositeChart
        h={180}
        data={data}
        dataKey="label"
        series={[
          { name: BOOKED_SERIES, color: "indigo.6", type: "bar" },
          { name: EXPECTED_SERIES, color: "gray.5", type: "line", strokeDasharray: "4 4" },
        ]}
        withLegend
        legendProps={{ verticalAlign: "bottom", height: 28 }}
        withTooltip
        valueFormatter={formatHoursValue}
        withDots={false}
        gridAxis="y"
      />
    </DashboardCard>
  );
}
