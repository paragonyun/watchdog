import { redirect } from "next/navigation";

import { hasValidSession } from "@/lib/auth";

import { loginAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if (await hasValidSession()) {
    redirect("/dashboard");
  }
  const params = await searchParams;
  const hasError = params.error === "1";

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <p className="eyebrow">Portfolio Watchdog</p>
        <h1 id="login-title">Private dashboard</h1>
        <form action={loginAction} className="login-form">
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" required />
          {hasError ? <p className="form-error">비밀번호가 맞지 않습니다.</p> : null}
          <button type="submit">Sign in</button>
        </form>
      </section>
    </main>
  );
}
