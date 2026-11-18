import { redirect } from "next/navigation";

export const metadata = { title: "Convert" };

export default function Page() {
  redirect("/convert");
}
