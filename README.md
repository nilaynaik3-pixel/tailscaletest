# Friends Connection Test for Home Assistant

A tiny helper that checks whether two Home Assistants can reach each other
over [Tailscale](https://tailscale.com), before you set up Friends in
[Workout Tracker](https://github.com/nilaynaik3-pixel/ha-workout-tracker).
It doesn't change anything else; remove it when you're done.

## Install (both of you)

1. HACS > three dots (top right) > **Custom repositories** >
   `https://github.com/nilaynaik3-pixel/tailscaletest`,
   type **Integration** > **Add**.
2. Search HACS for **Friends Connection Test** > **Download**, then restart
   Home Assistant.
3. Settings > Devices & services > **Add integration** >
   **Friends Connection Test** > **Submit**.

## Tailscale (both of you)

1. Tailscale add-on > **Configuration**: turn **off** *Userspace
   networking*, save, and restart the add-on. Otherwise Home Assistant can
   be reached over Tailscale but can't reach anyone else.
2. [Tailscale admin console](https://login.tailscale.com/admin/machines) >
   your Home Assistant machine > **Share...**, send the link to your friend,
   who accepts it. Do this both ways: sharing only works in one direction.

## Check

- Right after setup a notification shows **your Tailscale address** (give
  it to your friend) and whether your own address works.
- **Developer tools > Actions > Friends Connection Test: Check a friend's
  Home Assistant**, enter your friend's Tailscale address (e.g.
  `100.101.102.103`) and **Perform action**. The answer appears below the
  button and as a notification, with things to check if it fails.

Green in both directions (you check them, they check you) means Workout
Tracker's Friends feature will be able to connect.

## Remove

Settings > Devices & services > Friends Connection Test > three dots >
**Delete**, then HACS > Friends Connection Test > three dots > **Remove**,
and restart.

## How it works

It answers `GET /api/friends_connection_test/ping` without login (it only
returns its name), and the check fetches `/manifest.json` and that ping from
the address you enter.

## License

MIT
