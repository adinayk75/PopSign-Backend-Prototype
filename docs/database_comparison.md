# Database Comparison

## Goal

Choose a backend storage approach for PopSign's ASL video catalog that supports:

- multiple meanings for the same vocabulary word
- contextual tags for each meaning
- fast retrieval during story playback
- scalable video storage
- simple integration with the existing AWS-based backend

## Option 1: DynamoDB + S3

### Pros

- Fits naturally with the current AWS architecture.
- DynamoDB is serverless and requires little operational maintenance.
- Fast key-based lookup for a target word and its candidate meanings.
- Easy to store flexible metadata such as `sense`, `tags`, and `video_key`.
- S3 is well suited for large video files and scales independently from metadata.
- Low-cost prototype path with room to scale.

### Cons

- More awkward than SQL for complex joins and highly relational queries.
- Data access patterns need to be considered up front.
- Local development is slightly less direct than reading a JSON file.

### Verdict

**Recommended production direction.** Keep ASL video objects in S3 and searchable sign metadata in DynamoDB.

---

## Option 2: PostgreSQL / Amazon RDS

### Pros

- Strong structured querying and relational modeling.
- Easy to enforce relationships and constraints.
- Flexible if future requirements involve many related tables, analytics, or complex filters.
- Familiar SQL tooling.

### Cons

- More infrastructure and maintenance than DynamoDB for this use case.
- Requires database instance/configuration management.
- Video files still should not be stored directly in the relational database, so S3 would still be needed.
- Current sign lookup pattern does not require relational joins.

### Verdict

A good option if PopSign's data model becomes heavily relational, but likely unnecessary for the current sign-selection problem.

---

## Option 3: JSON metadata + S3

### Pros

- Simplest implementation.
- No database setup.
- Easy to inspect and modify while prototyping.
- Good for demonstrating matching logic quickly.

### Cons

- Poor concurrent update behavior.
- Requires reading/filtering larger files as the catalog grows.
- Harder to query efficiently.
- No built-in indexing.
- Not ideal for a production application with frequent updates.

### Verdict

**Best prototype format, not the recommended final storage layer.** This repository uses JSON so the contextual matching logic can be tested without AWS credentials.

---

## Recommendation

Use the following production split:

```text
DynamoDB
  word + sense + tags + video_key + metadata
             |
             v
Context Matcher / API
             |
             v
S3
  actual .mp4 ASL video objects
```

A possible DynamoDB item is:

```json
{
  "word": "rock",
  "sense": "music",
  "tags": ["music", "song", "band", "concert", "guitar"],
  "video_key": "asl/rock/music.mp4",
  "default": false
}
```

For a production table, a practical access pattern would be to query all candidate senses for one vocabulary word. One possible key design is:

- partition key: `word`
- sort key: `sense`

The application can then score those candidate records against the generated story context and return the best matching `video_key`.

## Why MCP is not required

MCP can be useful as a standardized way for an AI client to call external tools, but the actual contextual sign-selection algorithm does not require it. The backend already has the information needed:

1. story text
2. target vocabulary word
3. candidate meanings and context tags

A normal Python function or API endpoint can perform the lookup and return the matching video. MCP could be added later as another interface to the same function if the team has a specific agent/tooling use case.
