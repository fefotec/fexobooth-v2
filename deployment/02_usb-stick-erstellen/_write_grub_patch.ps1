# Fallback: GRUB-Bootmenue inline patchen
# Wird nur verwendet wenn tools/grub_menu_patch.txt nicht existiert
param(
    [string]$GrubCfgPath,
    [string]$OriginalPath
)

$patch = @'
set default="0"
set timeout="10"

menuentry "FexoBooth IMAGE AUFSPIELEN (Tablet klonen)" --id fexobooth-deploy {
  search --set -f /live/vmlinuz
  linux /live/vmlinuz boot=live union=overlay username=user config quiet noswap edd=on nomodeset locales="de_DE.UTF-8" keyboard-layouts="de" ocs_live_run="/live/custom-ocs/custom-ocs-deploy" ocs_live_extra_param="" ocs_live_batch="no" vga=788 ip= net.ifnames=0 nosplash noprompt
  initrd /live/initrd.img
}

menuentry "FexoBooth IMAGE ERSTELLEN (Referenz-Tablet abbilden)" --id fexobooth-capture {
  search --set -f /live/vmlinuz
  linux /live/vmlinuz boot=live union=overlay username=user config quiet noswap edd=on nomodeset locales="de_DE.UTF-8" keyboard-layouts="de" ocs_live_run="/live/custom-ocs/custom-ocs-capture" ocs_live_extra_param="" ocs_live_batch="no" vga=788 ip= net.ifnames=0 nosplash noprompt
  initrd /live/initrd.img
}

menuentry "-------------------------------------------" {
  true
}
'@

$orig = Get-Content $OriginalPath -Raw
Set-Content $GrubCfgPath -Value ($patch + "`n`n" + $orig) -Encoding UTF8
