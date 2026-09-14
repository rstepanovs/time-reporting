import { createBrowserRouter, type RouteObject } from "react-router";

import { RequireAuth } from "@/auth/RequireAuth";
import { AppLayout } from "@/components/AppLayout";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ProjectDetailsPage } from "@/pages/ProjectDetailsPage";
import { ProjectsPage } from "@/pages/ProjectsPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/",
        element: <AppLayout />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "projects", element: <ProjectsPage /> },
          { path: "projects/:projectId", element: <ProjectDetailsPage /> },
          { path: "account/password", element: <ChangePasswordPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
