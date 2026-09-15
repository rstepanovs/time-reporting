import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { RequireAuth } from "@/auth/RequireAuth";
import { RequireRole } from "@/auth/RequireRole";
import { AppLayout } from "@/components/AppLayout";
import { AdminCalendarPage } from "@/pages/admin/AdminCalendarPage";
import { AdminCustomersPage } from "@/pages/admin/AdminCustomersPage";
import { AdminProjectsPage } from "@/pages/admin/AdminProjectsPage";
import { AdminSystemStatusPage } from "@/pages/admin/AdminSystemStatusPage";
import { AdminUsersPage } from "@/pages/admin/AdminUsersPage";
import { ApprovalsPage } from "@/pages/ApprovalsPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HoursPage } from "@/pages/HoursPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ProjectDetailsPage } from "@/pages/ProjectDetailsPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { TimesheetPage } from "@/pages/TimesheetPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/",
        element: <AppLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "timesheet", element: <TimesheetPage /> },
          { path: "hours", element: <HoursPage /> },
          {
            path: "approvals",
            element: <RequireRole roles={["admin", "project_manager"]} />,
            children: [{ index: true, element: <ApprovalsPage /> }],
          },
          { path: "projects", element: <ProjectsPage /> },
          { path: "projects/:projectId", element: <ProjectDetailsPage /> },
          { path: "account/password", element: <ChangePasswordPage /> },
          {
            path: "admin",
            element: <RequireRole roles={["admin"]} />,
            children: [
              { index: true, element: <Navigate to="users" replace /> },
              { path: "users", element: <AdminUsersPage /> },
              { path: "customers", element: <AdminCustomersPage /> },
              { path: "projects", element: <AdminProjectsPage /> },
              { path: "calendar", element: <AdminCalendarPage /> },
              { path: "status", element: <AdminSystemStatusPage /> },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
