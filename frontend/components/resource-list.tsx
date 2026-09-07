import type { ResourceCollection, ResourceSummary } from "@/lib/api/resources";

function formatUpdatedAt(value: string): string | undefined {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function ResourceCard({ resource }: { readonly resource: ResourceSummary }) {
  const updatedAt = resource.updatedAt
    ? formatUpdatedAt(resource.updatedAt)
    : undefined;
  const occursAt = resource.occursAt
    ? formatUpdatedAt(resource.occursAt)
    : undefined;
  return (
    <article className="resource-card">
      <div className="resource-card-heading">
        <div>
          <h2>{resource.title}</h2>
          {resource.subtitle ? <p>{resource.subtitle}</p> : null}
        </div>
        {resource.status ? (
          <span className="status-pill">{resource.status}</span>
        ) : null}
      </div>
      <dl className="resource-metadata">
        {resource.code ? (
          <div>
            <dt>Code</dt>
            <dd>{resource.code}</dd>
          </div>
        ) : null}
        {updatedAt ? (
          <div>
            <dt>Updated</dt>
            <dd>{updatedAt}</dd>
          </div>
        ) : null}
        {occursAt ? (
          <div>
            <dt>When</dt>
            <dd>{occursAt}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

export function ResourceList({
  collection,
}: {
  readonly collection: ResourceCollection;
}) {
  return (
    <section aria-labelledby="record-count">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Current records</p>
          <h2 id="record-count">
            {collection.total === null
              ? "Available results"
              : `${collection.total.toLocaleString()} result${collection.total === 1 ? "" : "s"}`}
          </h2>
        </div>
      </div>
      <div className="resource-grid">
        {collection.items.map((resource) => (
          <ResourceCard key={resource.id} resource={resource} />
        ))}
      </div>
    </section>
  );
}
