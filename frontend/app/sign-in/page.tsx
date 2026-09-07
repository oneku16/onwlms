import { SignInForm } from "@/components/sign-in-form";

export const metadata = { title: "Sign in" };

export default function SignInPage() {
  return (
    <main className="auth-page" id="main-content">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="tenant-mark" aria-hidden="true">
            O
          </span>
          <div>
            <p className="product-name">OwnSIS</p>
            <p>Education administration</p>
          </div>
        </div>
        <p className="eyebrow">Secure institutional access</p>
        <h1>Sign in through OwnID</h1>
        <p>
          OwnID is the only human identity provider for OwnSIS. Your
          organization, roles, permissions, and entitlements are resolved after
          authentication.
        </p>
        <SignInForm />
        <p className="security-note">
          OwnSIS keeps identity-provider tokens on the server and uses secure
          cookies for the browser session.
        </p>
      </section>
    </main>
  );
}
