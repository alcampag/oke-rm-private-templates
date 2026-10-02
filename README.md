# OKE RM Private Templates

Install the published [OKE RM networking and cluster configurations](https://github.com/oracle-devrel/technology-engineering/tree/main/oci-and-db/cloud-native/devops-and-containers/oke/oke-rm)
as reusable private templates in your OCI tenancy. This installer creates templates only:
it does not create stacks, clusters, network resources, or IAM policies.

[![Open in Code Editor](https://raw.githubusercontent.com/oracle-devrel/oci-code-editor-samples/main/images/open-in-code-editor.png)](https://cloud.oracle.com/?region=home&cs_repo_url=https%3A%2F%2Fgithub.com%2Falcampag%2Foke-rm-private-templates.git&cs_branch=main&cs_initscript_path=install-private-templates.sh&cs_readme_path=README.md&cs_open_ce=true)

## Quick Start

1. Open the button above and review the repository before authorizing cloning.
2. If automatic execution does not start, open Cloud Shell in the cloned repository and run:

   ```bash
   bash install-private-templates.sh
   ```

3. Review the summary and type `yes` to create the templates.
4. In Resource Manager, create a stack and select a private template from the chosen compartment.

Oracle can disable automatic script execution for untrusted repositories.
The manual command is the supported fallback; see the
[Cloud Shell button documentation](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_using_git_from_code_editor_one_click_clone.htm).

## Inputs And Defaults

| Input | Default |
| --- | --- |
| Region | Current Cloud Shell region, or OCI CLI profile region |
| Template compartment | Current tenancy OCID (root compartment); editable |
| Templates | Both networking and cluster |
| Release version | Most recently published stable `oke-rm` release |
| Networking template name | `oke-rm-networking` |
| Cluster template name | `oke-rm-cluster` |
| Confirmation | No |

The release version is recorded in descriptions and free-form tags, not in the default names.
Both templates use the same release. The installer downloads published `infra.zip` and
`oke.zip` assets; it never rebuilds unreviewed source from `main`.
If the tenancy or region cannot be detected, enter it when prompted.
Kubernetes and deployment settings are configured later when creating a stack.

## Permissions And Safety

Use an identity authorized to list and create Resource Manager private templates in the
selected compartment and region. Root-compartment placement requires corresponding
permissions; choose a child compartment otherwise. Permissions are not created by this script.
Internet access to GitHub is required, as are OCI CLI and Python 3 (available in Cloud Shell).

Matching active templates created by this installer for the same version are skipped.
A name collision, different version, or customized ownership tags causes an error rather
than an overwrite. For a newer release, choose different names or manage the existing
template explicitly. Display names are not unique in OCI, so ambiguous matches also fail.
Tags record provenance, not a cryptographic guarantee that nobody has edited a template.
Creation is not transactional: if OCI fails after creating one template, rerun the installer
and the matching successful template is skipped.

Test permissions and validate downloads without creating templates:

```bash
bash install-private-templates.sh --dry-run
```

## Local Validation

```bash
bash -n install-private-templates.sh
python3 -m unittest discover -s tests
```
