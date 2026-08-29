import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { onSignedOut, session } from "./api/client";
import { LOCALES, useStrings, type LocaleTag } from "./i18n/strings";
import { ApprovalsPage } from "./pages/Approvals";
import { AuditPage } from "./pages/Audit";
import { BookingsPage } from "./pages/Bookings";
import { DashboardPage } from "./pages/Dashboard";
import { DispatchPage } from "./pages/Dispatch";
import { DriversPage } from "./pages/Drivers";
import { FinancePage } from "./pages/Finance";
import { ImportVillagesPage } from "./pages/ImportVillages";
import { LocationsPage } from "./pages/Locations";
import { RoutesPage } from "./pages/Routes";
import { SettingsPage } from "./pages/Settings";
import { SignInPage } from "./pages/SignIn";
import { SettlementsPage } from "./pages/Settlements";
import { TripsPage } from "./pages/Trips";
import { VehicleApprovalsPage } from "./pages/VehicleApprovals";
import { VehiclesPage } from "./pages/Vehicles";

// Section 76, in the order an operator actually works: what is happening now,
// then what it is made of, then the money, then the settings.
const NAV = [
  { to: "/", labelKey: "admin.nav.dashboard", element: <DashboardPage /> },
  { to: "/dispatch", labelKey: "admin.nav.operations", element: <DispatchPage /> },
  { to: "/trips", labelKey: "admin.nav.trips", element: <TripsPage /> },
  { to: "/bookings", labelKey: "admin.nav.bookings", element: <BookingsPage /> },
  { to: "/drivers", labelKey: "admin.nav.drivers", element: <DriversPage /> },
  { to: "/approvals", labelKey: "admin.nav.approvals", element: <ApprovalsPage /> },
  { to: "/vehicles", labelKey: "admin.nav.vehicles", element: <VehiclesPage /> },
  {
    to: "/vehicle-approvals",
    labelKey: "admin.nav.vehicle_approvals",
    element: <VehicleApprovalsPage />,
  },
  { to: "/settlements", labelKey: "admin.nav.settlements", element: <SettlementsPage /> },
  { to: "/locations", labelKey: "admin.nav.locations", element: <LocationsPage /> },
  { to: "/import", labelKey: "admin.nav.import", element: <ImportVillagesPage /> },
  { to: "/routes", labelKey: "admin.nav.routes", element: <RoutesPage /> },
  { to: "/finance", labelKey: "admin.nav.finance", element: <FinancePage /> },
  { to: "/settings", labelKey: "admin.nav.settings", element: <SettingsPage /> },
  { to: "/audit", labelKey: "admin.nav.audit", element: <AuditPage /> },
];

export function App() {
  const { t, ready, locale, setLocale } = useStrings();
  const [signedIn, setSignedIn] = useState(session.isSignedIn);

  useEffect(
    // A revoked or expired session returns to sign-in wherever the operator
    // happened to be, rather than leaving a page of failed requests.
    () => onSignedOut(() => setSignedIn(false)),
    [],
  );

  // Holding the first paint until the strings are in avoids a flash of raw
  // message keys, which looks broken.
  if (!ready) return null;

  if (!signedIn) return <SignInPage onSignedIn={() => setSignedIn(true)} />;

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">{t("app.name")}</div>
        {NAV.map((entry) => (
          <NavLink
            key={entry.to}
            to={entry.to}
            end={entry.to === "/"}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            {t(entry.labelKey)}
          </NavLink>
        ))}

        <div style={{ flex: 1 }} />

        <div className="row" style={{ gap: "var(--s-1)", padding: "var(--s-2)" }}>
          {LOCALES.map((entry) => (
            <button
              key={entry.tag}
              className={`small${entry.tag === locale ? " on" : ""}`}
              onClick={() => setLocale(entry.tag as LocaleTag)}
            >
              {entry.label}
            </button>
          ))}
        </div>
        <button
          className="small"
          style={{ margin: "var(--s-2)" }}
          onClick={() => {
            session.clear();
            setSignedIn(false);
          }}
        >
          {t("auth.action.sign_out")}
        </button>
      </nav>

      <main className="main">
        <Routes>
          {NAV.map((entry) => (
            <Route key={entry.to} path={entry.to} element={entry.element} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
