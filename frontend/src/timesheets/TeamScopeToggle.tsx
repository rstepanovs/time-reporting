import { SegmentedControl } from "@mantine/core";

import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage } from "@/auth/roles";
import type { TeamScope } from "@/timesheets/api";

type Props = {
  scope: TeamScope;
  onScopeChange: (scope: TeamScope) => void;
};

/** "My projects / All" toggle for the manager team views. Available to any manager — it's only
 * ever rendered inside a manager-only view anyway, so this check is effectively always true. */
export function TeamScopeToggle({ scope, onScopeChange }: Props) {
  const user = useAuthenticatedUser();
  if (!canManage(user)) return null;

  return (
    <SegmentedControl
      size="xs"
      value={scope}
      onChange={(value) => onScopeChange(value as TeamScope)}
      data={[
        { label: "My projects", value: "mine" },
        { label: "All", value: "all" },
      ]}
    />
  );
}
