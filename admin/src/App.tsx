import { useEffect, useState, type ReactElement } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { onSignedOut, session } from "./api/client";
import { fetchMe, hasAnyRole, isStaff, ME_KEY, OPERATIONS_ROLES, useRoles } from "./api/roles";
import { LOCALES, useStrings, type LocaleTag } from "./i18n/strings";
import { ApprovalsPage } from "./pages/Approvals";
import { AuditPage } from "./pages/Audit";
import { SupportPage } from "./pages/Support";
import { BookingsPage } from "./pages/Bookings";
import { DashboardPage } from "./pages/Dashboard";
import { DispatchPage } from "./pages/Dispatch";
import { DriversPage } from "./pages/Drivers";
import { PassengerPage } from "./pages/Passenger";
import { PassengersPage } from "./pages/Passengers";
import { FinancePage } from "./pages/Finance";
import { ImportVillagesPage } from "./pages/ImportVillages";
import { LocationsPage } from "./pages/Locations";
import { RoutesPage } from "./pages/Routes";
import { SettingsPage } from "./pages/Settings";
import { SignInPage } from "./pages/SignIn";
import { NegotiationsPage } from "./pages/Negotiations";
import { SettlementsPage } from "./pages/Settlements";
import { TripsPage } from "./pages/Trips";
import { VehicleApprovalsPage } from "./pages/VehicleApprovals";
import { VehiclesPage } from "./pages/Vehicles";

interface NavEntry {
  to: string;
  labelKey: string;
  element: ReactElement;
  /** Only these roles see the entry. None given: every staff role does. */
  roles?: ReadonlySet<string>;
}

// Section 76, in the order an operator actually works: what is happening now,
// then what it is made of, then the money, then the settings.
const NAV: NavEntry[] = [
  { to: "/", labelKey: "admin.nav.dashboard", element: <DashboardPage /> },
  { to: "/dispatch", labelKey: "admin.nav.operations", element: <DispatchPage /> },
  { to: "/trips", labelKey: "admin.nav.trips", element: <TripsPage /> },
  {
    to: "/negotiations",
    labelKey: "admin.nav.negotiations",
    element: <NegotiationsPage />,
  },
  { to: "/bookings", labelKey: "admin.nav.bookings", element: <BookingsPage /> },
  { to: "/drivers", labelKey: "admin.nav.drivers", element: <DriversPage /> },
  {
    to: "/passengers",
    labelKey: "admin.nav.passengers",
    element: <PassengersPage />,
    // Names, phone numbers and the off switch: the server serves this list
    // to operations roles only, and the sidebar does not offer the others a
    // page that can only answer "not allowed".
    roles: OPERATIONS_ROLES,
  },
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
  { to: "/support", labelKey: "admin.nav.support", element: <SupportPage /> },
  { to: "/audit", labelKey: "admin.nav.audit", element: <AuditPage /> },
];

export function App() {
  const { t, ready, locale, setLocale, forErrorCode } = useStrings();
  const client = useQueryClient();
  const [signedIn, setSignedIn] = useState(session.isSignedIn);
  const [notice, setNotice] = useState<string | null>(null);
  // Null until known. An entry limited to some roles is shown meanwhile: the
  // server decides either way, and a sidebar that grows an entry a moment
  // after opening is better than one that hides a page on a slow line.
  const roles = useRoles(signedIn);

  useEffect(
    // A revoked or expired session returns to sign-in wherever the operator
    // happened to be, rather than leaving a page of failed requests. Whose
    // roles they were goes with it, so the next person to sign in on this
    // browser is not shown the last one's sidebar.
    () =>
      onSignedOut(() => {
        client.removeQueries({ queryKey: ME_KEY });
        setSignedIn(false);
      }),
    [client],
  );

  useEffect(() => {
    if (!signedIn) return;
    // The roles were checked when the code was verified -- but a role can be
    // taken away afterwards, and the refresh token outlives it: the seed
    // administrator's session stayed open for weeks after its role was
    // revoked, showing every page and a 403 on each. Ask again on every open.
    // A failed request proves nothing about roles, so it signs nobody out.
    //
    // Fetched into the shared cache rather than beside it, and never served
    // from it (staleTime 0): the sidebar and the pages read this same answer,
    // so what they show is decided by the roles just checked.
    let cancelled = false;
    client.fetchQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: 0 }).then((me) => {
      if (cancelled || isStaff(me.roles)) return;
      session.clear();
      client.removeQueries({ queryKey: ME_KEY });
      setNotice(forErrorCode("PERMISSION_DENIED"));
      setSignedIn(false);
    }, () => undefined);
    return () => {
      cancelled = true;
    };
  }, [signedIn, forErrorCode, client]);

  // Holding the first paint until the strings are in avoids a flash of raw
  // message keys, which looks broken.
  if (!ready) return null;

  if (!signedIn) {
    return (
      <SignInPage
        initialNotice={notice}
        onSignedIn={() => {
          setNotice(null);
          setSignedIn(true);
        }}
      />
    );
  }

  const visible = NAV.filter(
    (entry) => !entry.roles || roles === null || hasAnyRole(roles, entry.roles),
  );

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">{t("app.name")}</div>
        {visible.map((entry) => (
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
            client.removeQueries({ queryKey: ME_KEY });
            setSignedIn(false);
          }}
        >
          {t("auth.action.sign_out")}
        </button>
      </nav>

      <main className="main">
        <Routes>
          {/* Every route stays, whatever the sidebar shows: a page the roles
              cannot use answers with the server's refusal, which is clearer
              than being bounced to the dashboard with no reason given. */}
          {NAV.map((entry) => (
            <Route key={entry.to} path={entry.to} element={entry.element} />
          ))}
          {/* One passenger. Not in the sidebar -- it is reached from a row --
              but under /passengers, so that entry stays lit while it is open. */}
          <Route path="/passengers/:userId" element={<PassengerPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
