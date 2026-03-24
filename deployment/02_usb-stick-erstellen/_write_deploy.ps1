# Fallback: custom-ocs-deploy inline erstellen
# Wird nur verwendet wenn custom-ocs/custom-ocs-deploy nicht existiert
param([string]$OutputPath)

$script = @'
#!/bin/bash
echo '============================================'
echo '  FexoBooth - IMAGE AUFSPIELEN'
echo '============================================'
echo ''

# FEXODATEN mounten (Image liegt auf NTFS-Datenpartition)
NTFS_PART=$(blkid -t LABEL=FEXODATEN -o device 2>/dev/null | head -1)
if [ -n "$NTFS_PART" ]; then
    echo "FEXODATEN gefunden: $NTFS_PART"
    umount /home/partimag 2>/dev/null
    mkdir -p /home/partimag
    mount $NTFS_PART /home/partimag
    [ $? -eq 0 ] && echo "[OK] FEXODATEN gemountet" || echo "WARNUNG: Mount fehlgeschlagen!"
else
    echo "FEXODATEN nicht gefunden, nutze Standard-Speicher"
fi
echo ''

IMAGE_NAME=''
for dir in /home/partimag/fexobooth-image-*; do
    [ -d "$dir" ] && IMAGE_NAME=$(basename "$dir")
done

if [ -z "$IMAGE_NAME" ]; then
    echo "FEHLER: Kein Image gefunden!"
    ls -la /home/partimag/ 2>/dev/null
    read -p "Enter zum Neustarten..." dummy
    reboot
fi

echo "Image: $IMAGE_NAME"

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
    echo "FEHLER: Keine Ziel-Festplatte!"
    lsblk -d -o NAME,SIZE,TYPE,MODEL,TRAN
    read -p "Enter zum Neustarten..." dummy
    reboot
fi

echo "Ziel: /dev/$TARGET_DISK"
echo "ACHTUNG: Alle Daten werden ueberschrieben!"
/usr/sbin/ocs-sr -e1 auto -c -p reboot restoredisk "$IMAGE_NAME" "$TARGET_DISK"
'@

$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($OutputPath, $script.Replace("`r`n","`n"), $utf8)
