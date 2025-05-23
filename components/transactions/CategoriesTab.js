import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Switch,
  FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle } from 'react-native-svg';

// Sample category data
const categoryData = [
  {
    id: '1',
    name: 'Bills & Utilities',
    icon: 'document-text-outline',
    iconBgColor: '#0ea5e9',
    amount: -90.00,
    percentage: 100.0,
  }
];

export default function CategoriesTab() {
  const [activeFilter, setActiveFilter] = useState('Expenses');
  const [currentMonth, setCurrentMonth] = useState('May');
  const [includeBills, setIncludeBills] = useState(false);
  
  const handlePreviousMonth = () => {
    // Logic to go to previous month
    console.log('Previous month');
  };

  const handleNextMonth = () => {
    // Logic to go to next month
    console.log('Next month');
  };

  // Calculate total amount for the donut chart
  const totalAmount = categoryData.reduce((sum, category) => sum + Math.abs(category.amount), 0);

  const renderHeader = () => (
    <>
      {/* Filters and Month Selection */}
      <View style={styles.filtersContainer}>
        <View style={styles.filterToggle}>
          {['Expenses', 'Income'].map((filter) => (
            <TouchableOpacity
              key={filter}
              style={[
                styles.filterButton,
                activeFilter === filter && styles.activeFilterButton
              ]}
              onPress={() => setActiveFilter(filter)}
            >
              <Text
                style={[
                  styles.filterText,
                  activeFilter === filter && styles.activeFilterText
                ]}
              >
                {filter}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        
        <View style={styles.monthSelector}>
          <TouchableOpacity onPress={handlePreviousMonth}>
            <Ionicons name="chevron-back" size={24} color="#94a3b8" />
          </TouchableOpacity>
          <Text style={styles.monthText}>{currentMonth}</Text>
          <TouchableOpacity onPress={handleNextMonth}>
            <Ionicons name="chevron-forward" size={24} color="#94a3b8" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Donut Chart */}
      <View style={styles.chartContainer}>
        <View style={styles.donutChartContainer}>
          <Svg height="240" width="240" viewBox="0 0 100 100">
            {/* Background circle */}
            <Circle
              cx="50"
              cy="50"
              r="40"
              stroke="#1e293b"
              strokeWidth="1"
              fill="transparent"
            />
            {/* Donut chart */}
            <Circle
              cx="50"
              cy="50"
              r="35"
              stroke="#0ea5e9"
              strokeWidth="20"
              fill="transparent"
            />
            {/* Inner circle */}
            <Circle
              cx="50"
              cy="50"
              r="25"
              stroke="#1e293b"
              strokeWidth="1"
              fill="#0f172a"
            />
          </Svg>
          <View style={styles.donutCenterText}>
            <Text style={styles.donutLabel}>{activeFilter}</Text>
            <Text style={styles.donutAmount}>-${totalAmount}</Text>
          </View>
        </View>
      </View>

      {/* Include Bills Toggle */}
      <View style={styles.toggleContainer}>
        <View style={styles.toggleInfo}>
          <Ionicons name="information-circle-outline" size={24} color="#94a3b8" />
          <Text style={styles.toggleLabel}>Include Bills</Text>
        </View>
        <Switch
          value={includeBills}
          onValueChange={setIncludeBills}
          trackColor={{ false: "#1e293b", true: "#0ea5e9" }}
          thumbColor="#ffffff"
        />
      </View>
    </>
  );

  const renderCategoryItem = ({ item }) => (
    <View style={styles.categoryItem}>
      <View style={[styles.categoryIcon, { backgroundColor: item.iconBgColor }]}>
        <Ionicons name={item.icon} size={24} color="white" />
      </View>
      <View style={styles.categoryInfo}>
        <Text style={styles.categoryName}>{item.name}</Text>
        <Text style={styles.categoryPercentage}>{item.percentage.toFixed(1)} %</Text>
      </View>
      <Text style={styles.categoryAmount}>- ${Math.abs(item.amount).toFixed(2)}</Text>
    </View>
  );

  return (
    <FlatList
      data={categoryData}
      renderItem={renderCategoryItem}
      keyExtractor={item => item.id}
      ListHeaderComponent={renderHeader}
      contentContainerStyle={styles.listContent}
      showsVerticalScrollIndicator={false}
    />
  );
}

const styles = StyleSheet.create({
  listContent: {
    paddingBottom: 80, // Add padding for FAB
  },
  filtersContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  filterToggle: {
    flexDirection: 'row',
    backgroundColor: '#1e293b',
    borderRadius: 24,
    padding: 4,
  },
  filterButton: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
  },
  activeFilterButton: {
    backgroundColor: '#0c4a6e',
  },
  filterText: {
    fontSize: 16,
    color: '#94a3b8',
  },
  activeFilterText: {
    color: '#0ea5e9',
  },
  monthSelector: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  monthText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: 'white',
    marginHorizontal: 12,
  },
  chartContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 8,
  },
  donutChartContainer: {
    position: 'relative',
    width: 240,
    height: 240,
    alignItems: 'center',
    justifyContent: 'center',
  },
  donutCenterText: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
  },
  donutLabel: {
    fontSize: 18,
    color: 'white',
    marginBottom: 4,
  },
  donutAmount: {
    fontSize: 24,
    fontWeight: 'bold',
    color: 'white',
  },
  toggleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 8,
  },
  toggleInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  toggleLabel: {
    fontSize: 16,
    color: 'white',
    marginLeft: 8,
  },
  categoryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: '#1e293b',
  },
  categoryIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  categoryInfo: {
    flex: 1,
  },
  categoryName: {
    fontSize: 16,
    color: 'white',
    marginBottom: 4,
  },
  categoryPercentage: {
    fontSize: 14,
    color: '#94a3b8',
  },
  categoryAmount: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
  },
});