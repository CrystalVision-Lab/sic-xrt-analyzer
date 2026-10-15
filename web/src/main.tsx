import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DownloadPage, GuidePage, NotesPage } from "./Public";
import { Loading } from "./ui";
import "./style.css";
const Admin = lazy(() => import("./Admin"));
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DownloadPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/releases" element={<Navigate to="/notes" replace />} />
        <Route path="/guide" element={<GuidePage />} />
        <Route
          path="/admin/*"
          element={
            <Suspense fallback={<Loading />}>
              <Admin />
            </Suspense>
          }
        />
        <Route path="*" element={<GuidePage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
