package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.model.Measurement;
import com.funcoesodm.javaservice.repository.MeasurementRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * Gera arquivos GeoPackage (OGC GeoPackage 1.3.1) no servidor Java.
 *
 * Usa sqlite-jdbc para criar o banco SQLite sem qualquer dependência
 * de WebAssembly (WASM) no browser.
 *
 * Especificação: https://www.geopackage.org/spec131/index.html
 *
 * Tabelas criadas:
 *   gpkg_spatial_ref_sys   — sistemas de referência (EPSG:4326 ou UTM)
 *   gpkg_contents          — catálogo de feature tables
 *   gpkg_geometry_columns  — mapeamento coluna → tipo de geometria
 *   medicoes_linhas        — distance, height → LINESTRING
 *   medicoes_areas         — area, volume     → POLYGON
 *
 * Formato de geometria: GeoPackage Binary (GPB) com WKB interno.
 */
@Service
public class GeoPackageExportService {

    private static final Logger log = LoggerFactory.getLogger(GeoPackageExportService.class);
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final MeasurementRepository measurementRepository;
    private final ProjectRepository     projectRepository;

    @Autowired
    public GeoPackageExportService(MeasurementRepository measurementRepository,
                                   ProjectRepository projectRepository) {
        this.measurementRepository = measurementRepository;
        this.projectRepository     = projectRepository;
    }

    // ─── Pontos de entrada públicos ──────────────────────────────────────────────

    /**
     * Gera GeoPackage para todas as medições de um projeto.
     *
     * @param projectId   ID do projeto
     * @param coordFormat "wgs84" ou "utm"
     * @param targetEpsg  EPSG do fuso UTM de saída (ex: 32724). null = auto-detectar.
     */
    public byte[] generateForProject(Long projectId, String coordFormat, Integer targetEpsg) {
        if (!projectRepository.existsById(projectId)) {
            throw new ResourceNotFoundException("Projeto não encontrado: " + projectId);
        }
        List<Measurement> measurements =
            measurementRepository.findByProjectIdOrderByCreatedAtDesc(projectId);
        return buildGeoPackage(measurements, coordFormat, targetEpsg);
    }

    /**
     * Gera GeoPackage para medições de um chunk específico.
     */
    public byte[] generateForChunk(Long projectId, Long chunkId,
                                   String coordFormat, Integer targetEpsg) {
        if (!projectRepository.existsById(projectId)) {
            throw new ResourceNotFoundException("Projeto não encontrado: " + projectId);
        }
        List<Measurement> measurements =
            measurementRepository.findByProjectIdAndChunkIdOrderByCreatedAtDesc(projectId, chunkId);
        return buildGeoPackage(measurements, coordFormat, targetEpsg);
    }

    // ─── Construção do GeoPackage ────────────────────────────────────────────────

    private byte[] buildGeoPackage(List<Measurement> measurements,
                                   String coordFormat, Integer targetEpsg) {
        boolean useUtm = "utm".equalsIgnoreCase(coordFormat);
        int epsg = 4326;
        if (useUtm) {
            epsg = (targetEpsg != null) ? targetEpsg : detectEpsg(measurements);
        }

        Path tempFile = null;
        try {
            tempFile = Files.createTempFile("funcoesodm-gpkg-", ".gpkg");
            String jdbcUrl = "jdbc:sqlite:" + tempFile.toAbsolutePath();

            try (Connection conn = DriverManager.getConnection(jdbcUrl)) {
                conn.setAutoCommit(false);

                createRequiredTables(conn);
                insertSrs(conn, epsg);

                List<Measurement> lines = new ArrayList<>();
                List<Measurement> polys = new ArrayList<>();
                for (Measurement m : measurements) {
                    switch (m.getType()) {
                        case "distance", "height" -> lines.add(m);
                        case "area",     "volume" -> polys.add(m);
                    }
                }

                if (!lines.isEmpty()) buildFeatureTable(conn, "medicoes_linhas", false, lines, useUtm, epsg);
                if (!polys.isEmpty()) buildFeatureTable(conn, "medicoes_areas",  true,  polys,  useUtm, epsg);

                conn.commit();
            }

            return Files.readAllBytes(tempFile);

        } catch (Exception e) {
            log.error("Erro ao gerar GeoPackage", e);
            throw new RuntimeException("Falha ao gerar GeoPackage: " + e.getMessage(), e);
        } finally {
            if (tempFile != null) {
                try { Files.deleteIfExists(tempFile); } catch (IOException ignored) {}
            }
        }
    }

    // ─── Tabelas obrigatórias GeoPackage ─────────────────────────────────────────

    private void createRequiredTables(Connection conn) throws SQLException {
        try (Statement s = conn.createStatement()) {
            s.execute("""
                CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
                  srs_name                 TEXT    NOT NULL,
                  srs_id                   INTEGER NOT NULL PRIMARY KEY,
                  organization             TEXT    NOT NULL,
                  organization_coordsys_id INTEGER NOT NULL,
                  definition               TEXT    NOT NULL,
                  description              TEXT
                )""");

            s.execute("""
                CREATE TABLE IF NOT EXISTS gpkg_contents (
                  table_name  TEXT     NOT NULL PRIMARY KEY,
                  data_type   TEXT     NOT NULL,
                  identifier  TEXT     UNIQUE,
                  description TEXT     DEFAULT '',
                  last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                  min_x       REAL,
                  min_y       REAL,
                  max_x       REAL,
                  max_y       REAL,
                  srs_id      INTEGER,
                  FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                )""");

            s.execute("""
                CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
                  table_name         TEXT    NOT NULL,
                  column_name        TEXT    NOT NULL,
                  geometry_type_name TEXT    NOT NULL,
                  srs_id             INTEGER NOT NULL,
                  z                  TINYINT NOT NULL,
                  m                  TINYINT NOT NULL,
                  CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
                  FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                )""");

            // Entradas mínimas obrigatórias pelo padrão OGC
            s.execute("""
                INSERT OR IGNORE INTO gpkg_spatial_ref_sys
                  (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
                VALUES
                  ('Undefined cartesian SRS',  -1, 'NONE', -1, 'undefined', 'undefined cartesian SRS'),
                  ('Undefined geographic SRS',  0, 'NONE',  0, 'undefined', 'undefined geographic SRS')
                """);
        }
    }

    private void insertSrs(Connection conn, int epsg) throws SQLException {
        String srsName, definition, description;
        if (epsg == 4326) {
            srsName     = "WGS 84 geodetic";
            definition  = WKT_WGS84;
            description = "longitude/latitude decimal degrees on WGS 84 spheroid";
        } else {
            int zone    = epsg % 100;
            boolean south = epsg >= 32700;
            String ns   = south ? "S" : "N";
            srsName     = "WGS 84 / UTM zone " + zone + ns;
            definition  = buildUtmWkt(zone, south);
            description = "UTM zone " + zone + ns;
        }

        try (PreparedStatement ps = conn.prepareStatement("""
            INSERT OR IGNORE INTO gpkg_spatial_ref_sys
              (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
            VALUES (?, ?, 'EPSG', ?, ?, ?)
            """)) {
            ps.setString(1, srsName);
            ps.setInt   (2, epsg);
            ps.setInt   (3, epsg);
            ps.setString(4, definition);
            ps.setString(5, description);
            ps.executeUpdate();
        }
    }

    // ─── Feature table ───────────────────────────────────────────────────────────

    private void buildFeatureTable(Connection conn, String tableName, boolean isPolygon,
                                   List<Measurement> entries, boolean useUtm, int epsg)
        throws SQLException {

        try (Statement s = conn.createStatement()) {
            s.execute(String.format("""
                CREATE TABLE IF NOT EXISTS %s (
                  fid        INTEGER PRIMARY KEY AUTOINCREMENT,
                  geom       BLOB,
                  id_medicao TEXT,
                  nome       TEXT,
                  tipo       TEXT,
                  valor      REAL,
                  unidade    TEXT,
                  fonte      TEXT,
                  criado_em  TEXT
                )""", tableName));
        }

        double minX = Double.MAX_VALUE, minY = Double.MAX_VALUE;
        double maxX = -Double.MAX_VALUE, maxY = -Double.MAX_VALUE;

        Map<String, String> typeLabels = Map.of(
            "distance", "Distancia",
            "area",     "Area",
            "volume",   "Volume",
            "height",   "Altura"
        );

        String insertSql = String.format(
            "INSERT INTO %s (geom, id_medicao, nome, tipo, valor, unidade, fonte, criado_em) VALUES (?,?,?,?,?,?,?,?)",
            tableName
        );

        try (PreparedStatement ps = conn.prepareStatement(insertSql)) {
            for (Measurement m : entries) {
                double[][] coords = parseCoordinates(m.getCoordinatesJson());
                if (coords == null || coords.length == 0) continue;

                double[][] xyPts = toXY(coords, useUtm, epsg);

                // Fechar anel de polígono
                double[][] ring = xyPts;
                if (isPolygon && ring.length >= 3) {
                    double[] first = ring[0], last = ring[ring.length - 1];
                    if (first[0] != last[0] || first[1] != last[1]) {
                        ring = Arrays.copyOf(ring, ring.length + 1);
                        ring[ring.length - 1] = first.clone();
                    }
                }

                // Atualiza bbox global
                for (double[] pt : ring) {
                    if (pt[0] < minX) minX = pt[0];
                    if (pt[1] < minY) minY = pt[1];
                    if (pt[0] > maxX) maxX = pt[0];
                    if (pt[1] > maxY) maxY = pt[1];
                }

                byte[] gpb      = buildGPB(ring, isPolygon, epsg);
                String created  = m.getCreatedAt() != null ? m.getCreatedAt().format(ISO) : "";

                ps.setBytes (1, gpb);
                ps.setString(2, String.valueOf(m.getId()));
                ps.setString(3, m.getName());
                ps.setString(4, typeLabels.getOrDefault(m.getType(), m.getType()));
                ps.setDouble(5, m.getValue());
                ps.setString(6, m.getUnit());
                ps.setString(7, m.getDataSource());
                ps.setString(8, created);
                ps.addBatch();
            }
            ps.executeBatch();
        }

        String geomType = isPolygon ? "POLYGON" : "LINESTRING";

        try (PreparedStatement ps = conn.prepareStatement("""
            INSERT OR IGNORE INTO gpkg_geometry_columns
              (table_name, column_name, geometry_type_name, srs_id, z, m)
            VALUES (?, 'geom', ?, ?, 0, 0)""")) {
            ps.setString(1, tableName);
            ps.setString(2, geomType);
            ps.setInt   (3, epsg);
            ps.executeUpdate();
        }

        try (PreparedStatement ps = conn.prepareStatement("""
            INSERT OR IGNORE INTO gpkg_contents
              (table_name, data_type, identifier, description, last_change,
               min_x, min_y, max_x, max_y, srs_id)
            VALUES (?, 'features', ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?, ?, ?)""")) {
            ps.setString(1, tableName);
            ps.setString(2, tableName);
            ps.setString(3, "Medicoes tipo " + geomType.toLowerCase());
            ps.setDouble(4, minX == Double.MAX_VALUE ? 0 : minX);
            ps.setDouble(5, minY == Double.MAX_VALUE ? 0 : minY);
            ps.setDouble(6, maxX == -Double.MAX_VALUE ? 0 : maxX);
            ps.setDouble(7, maxY == -Double.MAX_VALUE ? 0 : maxY);
            ps.setInt   (8, epsg);
            ps.executeUpdate();
        }
    }

    // ─── GeoPackage Binary (GPB) encoding ────────────────────────────────────────

    /**
     * Codifica geometria no formato GeoPackage Binary (GPB).
     *
     *  Header (40 bytes):
     *    [0x47 'G'][0x50 'P'][version=0x00][flags=0x03][srs_id:int32LE][envelope:4×float64LE]
     *    flags=0x03: bit0=LE, bits1-3=01 (envelope com minX,maxX,minY,maxY)
     *
     *  WKB (little-endian):
     *    [byteOrder=0x01][type:uint32][numRings:uint32 se polygon][numPts:uint32][X:float64 Y:float64 × n]
     */
    private byte[] buildGPB(double[][] ring, boolean isPolygon, int srsId) {
        double minX = Double.MAX_VALUE, minY = Double.MAX_VALUE;
        double maxX = -Double.MAX_VALUE, maxY = -Double.MAX_VALUE;
        for (double[] pt : ring) {
            if (pt[0] < minX) minX = pt[0];
            if (pt[1] < minY) minY = pt[1];
            if (pt[0] > maxX) maxX = pt[0];
            if (pt[1] > maxY) maxY = pt[1];
        }

        // 40 = GPB header | wkbHeader = 1+4+4(se polygon)+4 | pontos = n×16
        int wkbHeaderSize = isPolygon ? 13 : 9;
        int totalSize     = 40 + wkbHeaderSize + ring.length * 16;

        ByteBuffer buf = ByteBuffer.allocate(totalSize);
        buf.order(ByteOrder.LITTLE_ENDIAN);

        // GPB header
        buf.put((byte) 0x47);           // 'G'
        buf.put((byte) 0x50);           // 'P'
        buf.put((byte) 0x00);           // version
        buf.put((byte) 0x03);           // flags: LE=1 + has_envelope_type1=2
        buf.putInt(srsId);              // srs_id
        buf.putDouble(minX);
        buf.putDouble(maxX);
        buf.putDouble(minY);
        buf.putDouble(maxY);

        // WKB
        buf.put((byte) 0x01);                       // byte order: LE
        buf.putInt(isPolygon ? 3 : 2);              // type: 2=LineString, 3=Polygon
        if (isPolygon) buf.putInt(1);               // numRings
        buf.putInt(ring.length);                    // numPoints
        for (double[] pt : ring) {
            buf.putDouble(pt[0]);                   // X
            buf.putDouble(pt[1]);                   // Y
        }

        return buf.array();
    }

    // ─── Auxiliares ──────────────────────────────────────────────────────────────

    /**
     * Converte JSON de coordenadas "[[lat,lng],[lat,lng],...]" → double[][].
     * Índice 0 = lat, índice 1 = lng (conforme armazenamento no banco).
     */
    private double[][] parseCoordinates(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            json = json.trim();
            if (!json.startsWith("[[")) return null;
            json = json.substring(1, json.length() - 1).trim();
            String[] parts = json.split("\\],\\s*\\[");
            double[][] result = new double[parts.length][2];
            for (int i = 0; i < parts.length; i++) {
                String part = parts[i].replaceAll("[\\[\\]\\s]", "");
                String[] nums = part.split(",");
                result[i][0] = Double.parseDouble(nums[0]); // lat
                result[i][1] = Double.parseDouble(nums[1]); // lng
            }
            return result;
        } catch (Exception e) {
            log.warn("Falha ao parsear coordenadas: {}", json);
            return null;
        }
    }

    /**
     * Converte [[lat,lng]] para [[X,Y]] no CRS de saída.
     * WGS84: X=lng, Y=lat (convenção OGC).
     * UTM:   X=easting, Y=northing.
     */
    private double[][] toXY(double[][] coords, boolean useUtm, int epsg) {
        double[][] result = new double[coords.length][2];
        if (!useUtm) {
            for (int i = 0; i < coords.length; i++) {
                result[i][0] = coords[i][1]; // lng → X
                result[i][1] = coords[i][0]; // lat → Y
            }
        } else {
            int zone      = epsg % 100;
            boolean south = epsg >= 32700;
            double cm     = (zone - 1) * 6.0 - 180.0 + 3.0; // meridiano central
            for (int i = 0; i < coords.length; i++) {
                double[] en = wgs84ToUtm(coords[i][0], coords[i][1], cm, south);
                result[i][0] = en[0]; // easting  → X
                result[i][1] = en[1]; // northing → Y
            }
        }
        return result;
    }

    /**
     * Conversão WGS84 (lat, lng) → UTM (easting, northing) em metros.
     * Implementa a fórmula de Transverse Mercator padrão (USGS).
     */
    private double[] wgs84ToUtm(double lat, double lng, double centralMeridian, boolean south) {
        final double a  = 6378137.0;
        final double f  = 1.0 / 298.257223563;
        final double e2 = 2 * f - f * f;
        final double k0 = 0.9996;

        double latRad = Math.toRadians(lat);
        double lonRad = Math.toRadians(lng - centralMeridian);

        double sinLat = Math.sin(latRad);
        double cosLat = Math.cos(latRad);
        double tanLat = Math.tan(latRad);

        double N = a / Math.sqrt(1 - e2 * sinLat * sinLat);
        double T = tanLat * tanLat;
        double C = (e2 / (1 - e2)) * cosLat * cosLat;
        double A = cosLat * lonRad;

        double M = a * (
              (1 - e2/4 - 3*e2*e2/64  - 5*e2*e2*e2/256)  * latRad
            - (3*e2/8  + 3*e2*e2/32   + 45*e2*e2*e2/1024) * Math.sin(2*latRad)
            + (15*e2*e2/256 + 45*e2*e2*e2/1024)            * Math.sin(4*latRad)
            - (35*e2*e2*e2/3072)                           * Math.sin(6*latRad)
        );

        double ep2 = e2 / (1 - e2);

        double easting = k0 * N * (
              A
            + (1 - T + C) * Math.pow(A, 3) / 6
            + (5 - 18*T + T*T + 72*C - 58*ep2) * Math.pow(A, 5) / 120
        ) + 500000.0;

        double northing = k0 * (
              M
            + N * tanLat * (
                  Math.pow(A, 2) / 2
                + (5 - T + 9*C + 4*C*C) * Math.pow(A, 4) / 24
                + (61 - 58*T + T*T + 600*C - 330*ep2) * Math.pow(A, 6) / 720
              )
        );
        if (south) northing += 10_000_000.0;

        return new double[]{ easting, northing };
    }

    /** Detecta EPSG UTM dominante pela primeira coordenada disponível. */
    private int detectEpsg(List<Measurement> measurements) {
        for (Measurement m : measurements) {
            double[][] coords = parseCoordinates(m.getCoordinatesJson());
            if (coords != null && coords.length > 0) {
                double lat = coords[0][0], lng = coords[0][1];
                int zone = (int) Math.floor((lng + 180) / 6) + 1;
                return lat >= 0 ? 32600 + zone : 32700 + zone;
            }
        }
        return 4326;
    }

    // ─── WKT de SRS ──────────────────────────────────────────────────────────────

    private static final String WKT_WGS84 =
        "GEOGCS[\"WGS 84\"," +
        "DATUM[\"WGS_1984\",SPHEROID[\"WGS 84\",6378137,298.257223563]]," +
        "PRIMEM[\"Greenwich\",0]," +
        "UNIT[\"degree\",0.0174532925199433]," +
        "AUTHORITY[\"EPSG\",\"4326\"]]";

    private String buildUtmWkt(int zone, boolean isSouth) {
        int cm     = (zone - 1) * 6 - 180 + 3;
        long falseN = isSouth ? 10_000_000L : 0L;
        String ns  = isSouth ? "S" : "N";
        int epsg   = isSouth ? 32700 + zone : 32600 + zone;
        return
            "PROJCS[\"WGS 84 / UTM zone " + zone + ns + "\"," +
            "GEOGCS[\"WGS 84\",DATUM[\"WGS_1984\",SPHEROID[\"WGS 84\",6378137,298.257223563]]," +
            "PRIMEM[\"Greenwich\",0],UNIT[\"degree\",0.0174532925199433]]," +
            "PROJECTION[\"Transverse_Mercator\"]," +
            "PARAMETER[\"latitude_of_origin\",0]," +
            "PARAMETER[\"central_meridian\"," + cm + "]," +
            "PARAMETER[\"scale_factor\",0.9996]," +
            "PARAMETER[\"false_easting\",500000]," +
            "PARAMETER[\"false_northing\"," + falseN + "]," +
            "UNIT[\"metre\",1],AUTHORITY[\"EPSG\",\"" + epsg + "\"]]";
    }
}
