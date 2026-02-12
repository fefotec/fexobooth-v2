# Fallback: custom-ocs-deploy inline erstellen
# Wird nur verwendet wenn custom-ocs/custom-ocs-deploy nicht existiert
param([string]$OutputPath)

$script = @'
#!/bin/bash
echo '============================================'
echo '  FexoBooth - IMAGE AUFSPIELEN'
echo '============================================'
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

if [ -b /dev/mmcblk0 ]; then
    TARGET_DISK=mmcblk0
elif [ -b /dev/nvme0n1 ]; then
    TARGET_DISK=nvme0n1
elif [ -b /dev/sda ]; then
    USB_DEV=$(mount | grep /home/partimag | awk '{print $1}' | sed 's/[0-9]*$//')
    if [ "/dev/sda" != "$USB_DEV" ]; then
        TARGET_DISK=sda
    elif [ -b /dev/sdb ]; then
        TARGET_DISK=sdb
    fi
fi

if [ -z "$TARGET_DISK" ]; then
    echo "FEHLER: Keine Ziel-Festplatte!"
    lsblk -d
    read -p "Enter zum Neustarten..." dummy
    reboot
fi

echo "Ziel: /dev/$TARGET_DISK"
echo "ACHTUNG: Alle Daten werden ueberschrieben!"
/usr/sbin/ocs-sr -e1 auto -c -p reboot restoredisk "$IMAGE_NAME" "$TARGET_DISK"
'@

$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($OutputPath, $script.Replace("`r`n","`n"), $utf8)
