import { Component, StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

class AppErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <main className="login-page" role="alert"><section className="login-card"><p className="eyebrow">PATIENT OPS AGENT</p><h1>页面暂时无法显示</h1><p>请刷新页面后重试；当前操作不会自动提交或取消预约。</p><button className="button button--primary" type="button" onClick={() => window.location.reload()}>刷新页面</button></section></main>;
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppErrorBoundary><App /></AppErrorBoundary>
  </StrictMode>,
);
