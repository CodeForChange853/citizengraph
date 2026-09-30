import { Link } from "react-router";

// Placeholder until stage 2 (home screen).
export default function Home() {
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-10">
      <h1 className="text-heading font-bold">Citizen Graph</h1>
      <p className="text-body">The home screen arrives in stage 2.</p>
      <Link className="text-body font-bold text-primary underline" to="/design">
        Open the design page
      </Link>
    </main>
  );
}
