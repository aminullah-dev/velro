import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ApiError } from "./api/client";
import { App } from "./App";
import { StringsProvider } from "./i18n/strings";
import "./styles.css";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failureCount, error) => {
        // A 409 or a 403 will not become true by asking again; only a transport
        // failure or a server error is worth retrying.
        if (error instanceof ApiError) {
          if (error.isAuthFailure) return false;
          if (error.httpStatus >= 400 && error.httpStatus < 500) return false;
        }
        return failureCount < 2;
      },
      refetchOnWindowFocus: true,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <StringsProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </StringsProvider>
    </QueryClientProvider>
  </StrictMode>,
);
