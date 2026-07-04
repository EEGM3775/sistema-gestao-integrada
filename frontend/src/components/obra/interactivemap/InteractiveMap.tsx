import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import styles from './InteractiveMap.module.css';

// Fix leaflet marker icons broken by bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

interface LatLng { lat: number; lng: number; }

interface Props {
  endereco: string;
  nomObra: string;
}

async function geocode(address: string): Promise<LatLng | null> {
  try {
    const q = encodeURIComponent(address + ', Brasil');
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'pt-BR' } }
    );
    const data = await r.json();
    if (data.length > 0) return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
  } catch {}
  return null;
}

const BRAZIL_CENTER: LatLng = { lat: -15.77, lng: -47.93 };

const InteractiveMap: React.FC<Props> = ({ endereco, nomObra }) => {
  const [position, setPosition] = useState<LatLng | null>(null);
  const [geocoding, setGeocoding] = useState(true);

  useEffect(() => {
    if (!endereco) { setGeocoding(false); return; }
    geocode(endereco).then(pos => {
      setPosition(pos);
      setGeocoding(false);
    });
  }, [endereco]);

  if (geocoding) {
    return <div className={styles.loading}>Localizando endereço…</div>;
  }

  const center = position ?? BRAZIL_CENTER;
  const zoom = position ? 15 : 4;

  return (
    <div className={styles.wrapper}>
      <MapContainer center={center} zoom={zoom} className={styles.map} key={`${center.lat},${center.lng}`}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {position && (
          <Marker position={position}>
            <Popup>
              <strong>{nomObra}</strong><br />
              {endereco}
            </Popup>
          </Marker>
        )}
      </MapContainer>
      {!position && (
        <p className={styles.fallback}>
          Endereço não encontrado no mapa.{' '}
          <a
            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(endereco)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir no Google Maps
          </a>
        </p>
      )}
    </div>
  );
};

export default InteractiveMap;
