import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def remove_namespace(tag):
    """Pašalina XML namespace iš žymos pavadinimo."""
    return tag.split("}", 1)[-1]


def parse_coordinates(text):
    """KML koordinates paverčia į GeoJSON koordinates."""
    coordinates = []

    if not text or not text.strip():
        return coordinates

    try:
        for item in text.strip().split():
            if not item.strip():
                continue
            
            values = item.split(",")

            if len(values) < 2:
                continue

            longitude = float(values[0])
            latitude = float(values[1])

            # GeoJSON naudoja [longitude, latitude]
            coordinates.append([longitude, latitude])
    except ValueError as e:
        print(f"⚠️ Klaida parskyrant koordinates: {e}")

    return coordinates


def find_first(element, name):
    """Randa pirmą XML elementą pagal pavadinimą."""
    if element is None:
        return None
    
    for child in element.iter():
        if remove_namespace(child.tag) == name:
            return child

    return None


def parse_geometry(placemark):
    """Iš KML Placemark objekto sukuria GeoJSON geometriją."""

    # Point
    point = find_first(placemark, "Point")
    if point is not None:
        coordinates_element = find_first(point, "coordinates")

        if coordinates_element is not None and coordinates_element.text:
            coordinates = parse_coordinates(coordinates_element.text)

            if coordinates:
                return {
                    "type": "Point",
                    "coordinates": coordinates[0],
                }

    # LineString
    line = find_first(placemark, "LineString")
    if line is not None:
        coordinates_element = find_first(line, "coordinates")

        if coordinates_element is not None and coordinates_element.text:
            coordinates = parse_coordinates(coordinates_element.text)

            if coordinates:
                return {
                    "type": "LineString",
                    "coordinates": coordinates,
                }

    # Polygon
    polygon = find_first(placemark, "Polygon")
    if polygon is not None:
        outer_boundary = find_first(polygon, "outerBoundaryIs")

        if outer_boundary is not None:
            linear_ring = find_first(outer_boundary, "LinearRing")
            
            if linear_ring is not None:
                coordinates_element = find_first(linear_ring, "coordinates")

                if coordinates_element is not None and coordinates_element.text:
                    coordinates = parse_coordinates(coordinates_element.text)

                    if coordinates:
                        return {
                            "type": "Polygon",
                            "coordinates": [coordinates],
                        }

    return None


def parse_properties(placemark):
    """Surenka Placemark pavadinimą ir ExtendedData reikšmes."""
    properties = {}

    for child in placemark:
        tag_name = remove_namespace(child.tag)

        if tag_name == "name":
            properties["name"] = child.text or ""

        elif tag_name == "description":
            properties["description"] = child.text or ""

        elif tag_name == "ExtendedData":
            for data in child.iter():
                if remove_namespace(data.tag) != "Data":
                    continue

                key = data.attrib.get("name")
                value_element = find_first(data, "value")

                if key:
                    properties[key] = (
                        value_element.text if value_element is not None else ""
                    )

    return properties


def find_kml_file(kmz_path):
    """Randa KML failą KMZ archyve."""
    try:
        with zipfile.ZipFile(kmz_path, "r") as archive:
            print(f"📦 KMZ faile rastas failai: {archive.namelist()}")
            
            kml_files = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".kml")
            ]

            if not kml_files:
                raise ValueError("❌ KMZ faile nerastas KML failas.")

            print(f"📄 Rasti KML failai: {kml_files}")

            # Dažniausiai pagrindinis failas yra doc.kml
            for kml_file in kml_files:
                if Path(kml_file).name.lower() == "doc.kml":
                    print(f"✓ Naudojamas: {kml_file}")
                    return archive.read(kml_file)

            selected = kml_files[0]
            print(f"✓ Naudojamas: {selected}")
            return archive.read(selected)
    except zipfile.BadZipFile:
        raise ValueError("❌ Failas nėra galiojantis ZIP/KMZ failas.")
    except FileNotFoundError:
        raise ValueError(f"❌ Failas nerastas: {kmz_path}")


def convert_kmz_to_geojson(input_path, output_path):
    """Konvertuoja KMZ failą į GeoJSON."""
    print(f"🔄 Konvertuojama: {input_path}")
    print(f"📍 Išvestis: {output_path}\n")
    
    try:
        kml_content = find_kml_file(input_path)
        print(f"✓ KML failas perskaitytas ({len(kml_content)} baitų)\n")

        root = ET.fromstring(kml_content)
        print(f"✓ KML išanalyzuota\n")

        features = []
        placemarks_count = 0

        for placemark in root.iter():
            if remove_namespace(placemark.tag) != "Placemark":
                continue

            placemarks_count += 1
            geometry = parse_geometry(placemark)

            if geometry is None:
                print(f"⚠️ Placemark #{placemarks_count}: Nėra geometrijos")
                continue

            properties = parse_properties(placemark)

            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            }

            features.append(feature)
            print(f"✓ Placemark #{placemarks_count}: {properties.get('name', 'Nenurodytas')} - {geometry['type']}")

        print(f"\n📊 Iš viso Placemark objektų: {placemarks_count}")
        print(f"✓ Sėkmingai konvertuota: {len(features)}")

        if len(features) == 0:
            print("\n⚠️ DĖMESIO: Nesurastas nė vienas objektas!")
            return

        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }

        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(geojson, file, ensure_ascii=False, indent=2)

        print(f"\n✅ Konvertavimas BAIGTAS!")
        print(f"📁 Failas išsaugotas: {output_path}")

    except Exception as e:
        print(f"\n❌ KLAIDA: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="KMZ failo konvertavimas į GeoJSON"
    )

    parser.add_argument(
        "input",
        help="Įvesties KMZ failas, pvz. zemelapis.kmz",
    )

    parser.add_argument(
        "output",
        help="Išvesties GeoJSON failas, pvz. zemelapis.geojson",
    )

    args = parser.parse_args()

    convert_kmz_to_geojson(args.input, args.output)


if __name__ == "__main__":
    main()
