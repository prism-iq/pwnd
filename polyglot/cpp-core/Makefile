# L Investigation - C++ Search Engine (Blood)
# Compiles to shared library for FFI with Rust/Go/Node

CXX = g++
CXXFLAGS = -std=c++17 -O3 -march=native -fPIC -Wall -Wextra
LDFLAGS = -shared -pthread

SRC_DIR = src
LIB_DIR = lib
BUILD_DIR = build

TARGET = $(LIB_DIR)/liblsearch.so
SOURCES = $(wildcard $(SRC_DIR)/*.cpp)
OBJECTS = $(patsubst $(SRC_DIR)/%.cpp,$(BUILD_DIR)/%.o,$(SOURCES))

.PHONY: all clean release debug install

all: dirs $(TARGET)

dirs:
	@mkdir -p $(BUILD_DIR) $(LIB_DIR)

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CXX) $(LDFLAGS) $^ -o $@
	@echo "Built $(TARGET)"

release: CXXFLAGS += -DNDEBUG -flto
release: all

debug: CXXFLAGS += -g -DDEBUG -fsanitize=address
debug: LDFLAGS += -fsanitize=address
debug: all

clean:
	rm -rf $(BUILD_DIR) $(LIB_DIR)/*.so

install: release
	cp $(TARGET) /usr/local/lib/
	ldconfig

# FFI header generation
header:
	@echo "// Auto-generated FFI header" > $(LIB_DIR)/lsearch.h
	@echo "#pragma once" >> $(LIB_DIR)/lsearch.h
	@echo "#include <stdint.h>" >> $(LIB_DIR)/lsearch.h
	@echo "" >> $(LIB_DIR)/lsearch.h
	@echo "typedef struct { int64_t id; float score; char snippet[256]; } CSearchResult;" >> $(LIB_DIR)/lsearch.h
	@echo "typedef struct { char type[32]; char value[256]; } CPattern;" >> $(LIB_DIR)/lsearch.h
	@echo "" >> $(LIB_DIR)/lsearch.h
	@echo "int l_search_init();" >> $(LIB_DIR)/lsearch.h
	@echo "int l_search_add(int64_t id, const char* content, const char* subject, const char* sender, int64_t timestamp);" >> $(LIB_DIR)/lsearch.h
	@echo "int l_search_query(const char* query, CSearchResult* results, int max_results);" >> $(LIB_DIR)/lsearch.h
	@echo "int l_search_extract(const char* text, CPattern* patterns, int max_patterns);" >> $(LIB_DIR)/lsearch.h
	@echo "int64_t l_search_count();" >> $(LIB_DIR)/lsearch.h
