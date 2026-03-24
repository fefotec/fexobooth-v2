# Fallback: custom-ocs-capture inline erstellen
# Wird nur verwendet wenn custom-ocs/custom-ocs-capture nicht existiert
param([string]$OutputPath)

$script = @'
#!/bin/bash
echo '============================================'
echo '  FexoBooth - IMAGE ERSTELLEN'
echo '============================================'
echo ''

# FEXODATEN mounten (Image auf NTFS-Datenpartition speichern)
NTFS_PART=$(blkid -t LABEL=FEXODATEN -o device 2>/dev/null | head -1)
if [ -n "$NTFS_PART" ]; then
    echo "FEXODATEN gefunden: $NTFS_PART"
    umount /home/partimag 2>/dev/null
    mkdir -p /home/partimag
    mount $NTFS_PART /home/partimag
    [ $? -eq 0 ] && echo "[OK] Image wird auf FEXODATEN gespeichert" || echo "WARNUNG: Mount fehlgeschlagen!"
else
    echo "FEXODATEN nicht gefunden, nutze Standard-Speicher"
fi
echo ''

# USB-Stick ermitteln und ausschliessen
USB_DISK=""
for mnt in /run/live/medium /home/partimag; do
    DEV=$(mount | grep " $mnt " | awk '{print $1}')
    [ -n "$DEV" ] && DISK=$(lsblk -no PKNAME "$DEV" 2>/dev/null | head -1) && [ -n "$DISK" ] && USB_DISK="$DISK"
done

TARGET_DISK=""
for dev in /dev/mmcblk[0-9] /dev/mmcblk[0-9][0-9] /dev/nvme[0-9]n[0-9] /dev/sd[a-z]; do
    if [ -b "$dev" ]; then
        DEVNAME=$(basename "$dev")
        [ "$DEVNAME" = "$USB_DISK" ] && continue
        case "$DEVNAME" in mmcblk*boot*) continue ;; esac
        TYPE=$(lsblk -no TYPE "$dev" 2>/dev/null | head -1)
        [ "$TYPE" != "disk" ] && continue
        TARGET_DISK="$DEVNAME"
        break
    fi
done

if [ -z "$TARGET_DISK" ]; then
    echo "FEHLER: Keine Festplatte gefunden!"
    lsblk -d -o NAME,SIZE,TYPE,MODEL,TRAN
    read -p "Enter zum Neustarten..." dummy
    reboot
fi

IMAGE_NAME=fexobooth-image-$(date +%Y%m%d)
echo "Disk: /dev/$TARGET_DISK  Image: $IMAGE_NAME"
echo ""
/usr/sbin/ocs-sr -q2 -c -j2 -z5 -i 4096 -sfsck -senc -p reboot savedisk "$IMAGE_NAME" "$TARGET_DISK"
'@

$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($OutputPath, $script.Replace("`r`n","`n"), $utf8)
