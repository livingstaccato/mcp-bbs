.PHONY: diagrams diagrams-svg diagrams-png help clean

# Default target
diagrams: diagrams-svg

# Generate diagrams in SVG format
diagrams-svg:
	@python3 docs/generate_diagrams.py --format svg

# Generate diagrams in PNG format
diagrams-png:
	@python3 docs/generate_diagrams.py --format png

# Clean generated diagram files
clean:
	@echo "Removing generated diagram files..."
	@rm -f docs/diagrams/*.svg docs/diagrams/*.png
	@echo "Done."

# Show available targets
help:
	@echo "Available targets:"
	@echo "  diagrams       - Generate all diagrams (SVG format, default)"
	@echo "  diagrams-svg   - Generate diagrams in SVG format"
	@echo "  diagrams-png   - Generate diagrams in PNG format"
	@echo "  clean          - Remove all generated diagram files"
	@echo "  help           - Show this help message"
