# Packaging manifests

Community-installer manifests for Sifty. Both install the standalone
`sifty.exe` that the [release workflow](../.github/workflows/release.yml)
attaches to each GitHub Release, so they can only be finalized **after** a
release exists (they need the exe's URL and SHA256).

## Filling the hash after a release

Once the release has published and `sifty.exe` is attached:

```powershell
# Download the released exe and print its SHA256 (uppercase)
$ver = "0.6.0"
$url = "https://github.com/Vortrix5/sifty/releases/download/v$ver/sifty.exe"
Invoke-WebRequest $url -OutFile sifty.exe
(Get-FileHash sifty.exe -Algorithm SHA256).Hash
```

Paste that value over `REPLACE_WITH_SHA256` in both `scoop/sifty.json` and
`winget/Vortrix5.Sifty.installer.yaml`.

## Scoop

`scoop/sifty.json` points at the GitHub release exe and has `checkver` +
`autoupdate`, so future versions are picked up automatically.

Install (without a bucket):

```powershell
scoop install https://raw.githubusercontent.com/Vortrix5/sifty/main/packaging/scoop/sifty.json
```

For a nicer `scoop install sifty`, publish a bucket repo (e.g.
`Vortrix5/scoop-bucket`) containing this file under `bucket/`, then
`scoop bucket add sifty https://github.com/Vortrix5/scoop-bucket`.

## winget

`winget/` holds the three manifests winget requires (version, installer,
locale) for a **portable** install (drops the exe, registers the `sifty`
command). To make `winget install Vortrix5.Sifty` work for everyone, submit
them to the community repo:

1. Validate locally: `winget validate --manifest packaging/winget`
2. Test install: `winget install --manifest packaging/winget`
3. Open a PR adding them under
   `manifests/v/Vortrix5/Sifty/0.6.0/` in
   [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs)
   (the `wingetcreate submit` tool automates this).
