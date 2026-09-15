import { SegmentedControl } from "@mantine/core";

import { useAuthenticatedUser } from "@/auth/hooks";
import { isAdmin } from "@/auth/roles";
import type { TeamScope } from "@/timesheets/api";

type Props = {
  scope: TeamScope;
  onScopeChange: (scope: TeamScope) => void;
};

/** "My projects / All" toggle for the manager team views. A project manager always sees their own
 * projects, so this renders nothing for them — only an admin can widen the scope. */
export function TeamScopeToggle({ scope, onScopeChange }: Props) {
  const user = useAuthenticatedUser();
  if (!isAdmin(user.role)) return null;

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
