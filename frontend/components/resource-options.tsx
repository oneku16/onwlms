import { resourceLabel, type ResourceSummary } from "@/lib/api/resources";

/** Render a placeholder plus one option per backend-provided resource. */
export function ResourceOptions({
  includeIdentifier = false,
  placeholder,
  resources,
}: {
  /** Append a short identifier so privacy-minimized entries stay distinguishable. */
  readonly includeIdentifier?: boolean;
  readonly placeholder: string;
  readonly resources: readonly ResourceSummary[];
}) {
  return (
    <>
      <option value="" disabled>
        {resources.length === 0 ? "No records are available" : placeholder}
      </option>
      {resources.map((resource) => (
        <option key={resource.id} value={resource.id}>
          {includeIdentifier
            ? `${resourceLabel(resource)} · ${resource.id.slice(0, 8)}`
            : resourceLabel(resource)}
        </option>
      ))}
    </>
  );
}
