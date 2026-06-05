"use server";

import { redirect } from "next/navigation";

import { clearSessionCookie, createSessionCookie, verifyLoginPassword } from "@/lib/auth";

export async function loginAction(formData: FormData): Promise<void> {
  const password = String(formData.get("password") || "");
  if (!(await verifyLoginPassword(password))) {
    redirect("/login?error=1");
  }
  await createSessionCookie();
  redirect("/dashboard");
}

export async function logoutAction(): Promise<void> {
  await clearSessionCookie();
  redirect("/login");
}
