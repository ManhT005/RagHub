# Provider credentials

Every provider connection owns one encrypted credential. Its catalog identity and
runtime type cannot change. Create a new connection when switching brands;
workspaces select models from the new connection. Multiple accounts of the same
brand remain independent. Runtime inference never reads a global provider API key.

Environment variables are optional bootstrap inputs. After migrations, import them
once for an explicit organization:

```sh
python -m app.cli.providers import-env --organization-id <organization-uuid>
```

Existing connections and manually rotated keys are preserved on repeated imports.
New connections remain UNTESTED; test them from System > AI Providers and register
models after authentication succeeds. Credentials never appear in API responses.

Existing Gemini installations that used GEMINI_API_KEY implicitly must run:

```sh
python -m app.cli.providers import-env --organization-id <organization-uuid> --fill-legacy-gemini
```

This fills only an empty Gemini connection credential. It does not replace a key
already configured by an admin. Remove bootstrap keys from the deployment environment
after import if desired. Rotate credentials from the connection's management form.
