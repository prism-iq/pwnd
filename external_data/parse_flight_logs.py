#!/usr/bin/env python3
"""Parse Epstein flight logs into structured JSON format for ingestion"""

import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Known abbreviations in flight logs
KNOWN_ABBREVS = {
    'JE': 'Jeffrey Epstein',
    'GM': 'Ghislaine Maxwell',
    'SK': 'Sarah Kellen',
    'AP': 'Adriana Ross',  # Also known as Adriana Mucinska
    'NM': 'Nadia Marcinkova',
    'LM': 'Les Wexner',
    'EMMY': 'Emmy Tayler',
}

# Airport codes
AIRPORTS = {
    'TIST': 'St. Thomas, USVI',
    'PBI': 'Palm Beach, FL',
    'LGA': 'LaGuardia, NY',
    'JFK': 'JFK, NY',
    'HPN': 'Westchester, NY',
    'EWR': 'Newark, NJ',
    'BED': 'Bedford, MA',
    'LFPB': 'Paris Le Bourget, France',
    'EGGW': 'Luton, UK',
    'ESSA': 'Stockholm, Sweden',
    'LFML': 'Marseille, France',
    'MIA': 'Miami, FL',
    'IAD': 'Washington Dulles, DC',
    'BGR': 'Bangor, ME',
    'ABQ': 'Albuquerque, NM',
    'CMH': 'Columbus, OH',
    'MBPV': 'Providenciales, Turks',
    'MPPV': 'Panama',
    'ABY': 'Albany, GA',
    'TEB': 'Teterboro, NJ',
    'SXM': 'St. Maarten',
    'SFO': 'San Francisco, CA',
    'LAX': 'Los Angeles, CA',
    'BOS': 'Boston, MA',
}

def expand_abbreviations(passengers: str) -> List[str]:
    """Expand known abbreviations and extract passenger names"""
    names = []
    # Split by commas
    parts = [p.strip() for p in passengers.split(',')]

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Skip generic entries
        if part.upper() in ['EMPTY', 'CARGO', 'FUEL ONLY']:
            continue

        # Handle "X FEMALE(S)" or "X MALE(S)"
        if re.match(r'\d+\s*(FEMALE|MALE)S?', part.upper()):
            match = re.match(r'(\d+)\s*(FEMALE|MALE)S?', part.upper())
            count = int(match.group(1))
            gender = match.group(2)
            for i in range(count):
                names.append(f'UNIDENTIFIED {gender}')
            continue

        # Handle "1 FEMALE" without number
        if part.upper() in ['FEMALE', 'MALE']:
            names.append(f'UNIDENTIFIED {part.upper()}')
            continue
        if part.upper() == '1 FEMALE':
            names.append('UNIDENTIFIED FEMALE')
            continue
        if part.upper() == '1 MALE':
            names.append('UNIDENTIFIED MALE')
            continue

        # Expand abbreviations
        if part.upper() in KNOWN_ABBREVS:
            names.append(KNOWN_ABBREVS[part.upper()])
        else:
            # Clean up the name
            name = part.strip()
            # Remove flight numbers or other numeric codes
            if re.match(r'^\d+$', name):
                continue
            if name:
                names.append(name)

    return names

def parse_flight_line(line: str) -> Dict[str, Any] | None:
    """Parse a single flight log line"""
    # Pattern: Date, Aircraft, Registration, From, To, Flight#, Passengers
    # Example: 6-Jan  B-727-31  N908JE  TIST  EWR  44 JE, GM, SK, AP, ALEXIA WALLERT

    # Various date formats
    date_patterns = [
        r'^(\d{1,2}-[A-Za-z]{3})',  # 6-Jan
        r'^([A-Za-z]{3}-\d{1,2})',  # Apr-15
        r'^(\d{4},\s*[A-Z]{3})',    # 2002, NOV
    ]

    # Try to extract date
    date_str = None
    for pattern in date_patterns:
        match = re.match(pattern, line.strip())
        if match:
            date_str = match.group(1)
            break

    if not date_str:
        return None

    # Look for aircraft and airports
    # Pattern with aircraft info
    aircraft_match = re.search(r'(B-727|G-1159|Gulfstream|G-IV|G-V)', line, re.IGNORECASE)
    aircraft = aircraft_match.group(1) if aircraft_match else 'Unknown'

    # Look for registration
    reg_match = re.search(r'(N\d{3}[A-Z]{2})', line)
    registration = reg_match.group(1) if reg_match else 'Unknown'

    # Look for airport codes (4 letters or less, all caps)
    airports = re.findall(r'\b([A-Z]{3,4})\b', line)
    # Filter to known airports
    from_airport = None
    to_airport = None
    for ap in airports:
        if ap in AIRPORTS:
            if not from_airport:
                from_airport = ap
            elif not to_airport:
                to_airport = ap

    # Extract passengers - everything after the flight number usually
    passengers_match = re.search(r'\d+\s+(.+?)(?:\d+/|\s*$)', line)
    passengers_str = passengers_match.group(1) if passengers_match else ''

    # Also try to get passengers from after the last airport code
    if to_airport:
        idx = line.rfind(to_airport)
        if idx > 0:
            after_dest = line[idx + len(to_airport):]
            # Skip flight number
            after_num = re.sub(r'^\s*\d+\s*', '', after_dest)
            if len(after_num) > len(passengers_str):
                passengers_str = after_num

    passengers = expand_abbreviations(passengers_str)

    if not from_airport and not to_airport and not passengers:
        return None

    return {
        'date_raw': date_str,
        'aircraft': aircraft,
        'registration': registration,
        'from_airport': from_airport,
        'from_location': AIRPORTS.get(from_airport, from_airport) if from_airport else None,
        'to_airport': to_airport,
        'to_location': AIRPORTS.get(to_airport, to_airport) if to_airport else None,
        'passengers': passengers,
        'passengers_raw': passengers_str.strip(),
        'raw_line': line.strip()[:200],
    }


def parse_flight_logs(filepath: str) -> List[Dict[str, Any]]:
    """Parse entire flight log file"""
    flights = []
    current_year = 2002  # Default start year

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Check for year markers
            year_match = re.match(r'^(\d{4})', line)
            if year_match and len(line) < 10:
                current_year = int(year_match.group(1))
                continue

            # Check for year in format "2002, NOV"
            year_match2 = re.match(r'^(\d{4}),\s*[A-Z]{3}', line)
            if year_match2:
                current_year = int(year_match2.group(1))

            # Parse the line
            flight = parse_flight_line(line)
            if flight:
                flight['year'] = current_year
                flights.append(flight)

    return flights


def extract_notable_passengers(flights: List[Dict]) -> Dict[str, int]:
    """Count passenger appearances"""
    counts = {}
    for flight in flights:
        for passenger in flight.get('passengers', []):
            name = passenger.upper()
            # Skip unidentified
            if 'UNIDENTIFIED' in name:
                continue
            counts[passenger] = counts.get(passenger, 0) + 1

    # Sort by count
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def main():
    log_file = Path(__file__).parent / 'flight_logs' / 'flight_logs.txt'

    if not log_file.exists():
        print(f"Flight logs not found at {log_file}")
        return

    print(f"Parsing {log_file}...")
    flights = parse_flight_logs(str(log_file))

    print(f"Parsed {len(flights)} flight records")

    # Save structured data
    output_file = Path(__file__).parent / 'flight_logs' / 'flights_structured.json'
    with open(output_file, 'w') as f:
        json.dump(flights, f, indent=2)
    print(f"Saved to {output_file}")

    # Extract passenger counts
    counts = extract_notable_passengers(flights)
    print("\nTop 20 passengers by flight count:")
    for name, count in list(counts.items())[:20]:
        print(f"  {name}: {count} flights")

    # Save passenger counts
    counts_file = Path(__file__).parent / 'flight_logs' / 'passenger_counts.json'
    with open(counts_file, 'w') as f:
        json.dump(counts, f, indent=2)
    print(f"\nSaved passenger counts to {counts_file}")

    # Find notable names
    notable = ['CLINTON', 'TRUMP', 'PRINCE', 'ANDREW', 'GATES', 'DERSHOWITZ', 'WEXNER']
    print("\nNotable name mentions:")
    for flight in flights:
        for passenger in flight.get('passengers', []):
            for notable_name in notable:
                if notable_name in passenger.upper():
                    print(f"  {flight.get('date_raw', '?')}/{flight.get('year', '?')}: {passenger} - {flight.get('from_airport')} to {flight.get('to_airport')}")
                    break


if __name__ == '__main__':
    main()
