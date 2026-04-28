import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

export function renderWithRouter(
  ui: ReactElement,
  {
    route = "/",
    path = "/",
    extraRoutes,
  }: {
    route?: string;
    path?: string;
    extraRoutes?: ReactNode;
  } = {},
) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
        {extraRoutes}
      </Routes>
    </MemoryRouter>,
  );
}
