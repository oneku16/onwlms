import Link from "next/link";

export default function NotFound() {
  return (
    <main className="standalone-state" id="main-content">
      <section className="state-panel">
        <p className="state-kicker">404</p>
        <h1>Page not found</h1>
        <p>The requested OwnSIS capability does not exist at this address.</p>
        <Link className="button" href="/dashboard">
          Return to dashboard
        </Link>
      </section>
    </main>
  );
}
