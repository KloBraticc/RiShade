<h1 align="center"><b>Rishade</b></h1>

<h5 align="center">Mini Project</h5>

<p align="center">
<img src="https://raw.githubusercontent.com/KloBraticc/RiShade/main/Images/RiShde.png" alt="preview" width="30%"/>
</p>

<p align="center">
  <a href="github.com/KloBraticc/RiShade/releases/latest">Latest release</a> |
  <a href="https://voidstrapp.netlify.app/donate/donate">Donate</a> |
  <a href="https://discord.gg/5tJBqBH8ck">Discord</a>
</p>

<div align="center">

[![Total Downloads][shield-repo-total]][repo-releases]
[![Latest Downloads][shield-repo-downloads]][repo-latest]
[![Latest Release][shield-repo-latest]][repo-latest]
[![Discord][shield-discord-server]][discord-invite]
[![Stars][shield-repo-stars]][repo-stargazers]

</div>

## Basic Rishade Preview

<div align="center">

<table>
  <tr>
    <td>
      <img src="https://raw.githubusercontent.com/KloBraticc/RiShade/main/Images/Image1.png" alt="RiShade Screenshot 1" width="380" style="margin:5px;">
    </td>
    <td>
      <img src="https://raw.githubusercontent.com/KloBraticc/RiShade/main/Images/Image2.png" alt="RiShade Screenshot 2" width="380" style="margin:5px;">
    </td>
  </tr>
  <tr>
    <td>
      <img src="https://raw.githubusercontent.com/KloBraticc/RiShade/main/Images/Untitled%20design%20(7).png" alt="RiShade Screenshot 3" width="380" style="margin:5px;">
    </td>
    <td>
      <img src="https://raw.githubusercontent.com/KloBraticc/RiShade/main/Images/image4.png" alt="RiShade Screenshot 4" width="380" style="margin:5px;">
    </td>
  </tr>
</table>

</div>

## How?

RiShade uses GLFW to create a transparent, on top OpenGL window that covers your entire screen.

1. Captures the current display using DXCam (or mss as fallback)
2. Uploads the frame to the GPU via double buffered PBO
3. Runs the frame through a chain of GLSL fragment shader
4. Composites the result back to the screen
5. Renders the imgui settings panel on top

---

# Shortcuts

## Keyboard

| Key | Action |
|---|---|
| `F8` | Toggle the settings panel |
| `P` | Exit RiShade |

## Settings Storage

| Path | Contents |
|---|---|
| `%LOCALAPPDATA%\RiShade\settings.json` | Current settings |
| `%LOCALAPPDATA%\RiShade\CreatedPresets\` | Saved custom presets |
| `%LOCALAPPDATA%\RiShade\shader_cache\` | Compiled shader binaries |

---

<p align="center">
  <a href="https://discord.gg/5tJBqBH8ck">
    <img src="https://invidget.switchblade.xyz/5tJBqBH8ck">
  </a>
</p>

## License

<table style="width: 100%; border-collapse: collapse;">
  <tr>
    <td style="width: 33%; text-align: left;">© RiShade</td>
    <td style="width: 33%; text-align: right;"><a href="https://github.com/KloBraticc/RiShade/blob/main/LICENSE" target="_blank">MIT</a></td>
  </tr>
</table>

> [!WARNING]
> RiShade is inspired by Bloxshade. Everything here is still a WIP.
> Features may change and some things may be unfinished.


[shield-repo-downloads]: https://img.shields.io/github/downloads/KloBraticc/RiShade/latest/total?color=981bfe
[shield-repo-total]:     https://img.shields.io/github/downloads/KloBraticc/RiShade/total?color=8a2be2
[shield-repo-latest]:    https://img.shields.io/github/v/release/KloBraticc/RiShade?color=7a39fb
[shield-repo-stars]:     https://img.shields.io/github/stars/KloBraticc/RiShade?color=ffd700
[shield-discord-server]: https://img.shields.io/discord/1327967202015580223?logo=discord&logoColor=white&label=Discord&color=4d3dff

[repo-releases]:         https://github.com/KloBraticc/RiShade/releases
[repo-latest]:           https://github.com/KloBraticc/RiShade/releases/latest
[repo-stargazers]:       https://github.com/KloBraticc/RiShade/stargazers
[discord-invite]:        https://discord.gg/dfA9PdWgcV
