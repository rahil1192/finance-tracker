import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

// Sample monthly data
const monthlyData = [
  {
    id: '1',
    month: 'May',
    amount: -90.00,
    percentage: 100, // For the progress bar
  }
];

export default function MonthlyTab() {
  const navigation = useNavigation();
  const [activeFilter, setActiveFilter] = useState('Expenses');
  
  const handleAddTransaction = () => {
    navigation.navigate('AddTransaction');
  };

  const handleMonthPress = (month) => {
    // Navigate to month details or expand month
    console.log(`Month pressed: ${month}`);
  };

  const renderMonthItem = ({ item }) => (
    <TouchableOpacity 
      style={styles.monthCard}
      onPress={() => handleMonthPress(item.month)}
    >
      <Text style={styles.monthName}>{item.month}</Text>
      <View style={styles.progressBarContainer}>
        <View 
          style={[
            styles.progressBar, 
            { width: `${item.percentage}%` }
          ]} 
        />
      </View>
      <Text style={styles.monthAmount}>- ${Math.abs(item.amount)}</Text>
    </TouchableOpacity>
  );

  const renderHeader = () => (
    <View style={styles.filterContainer}>
      {['All', 'Expenses', 'Income'].map((filter) => (
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
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={monthlyData}
        renderItem={renderMonthItem}
        keyExtractor={item => item.id}
        ListHeaderComponent={renderHeader}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
      />

      {/* Floating Action Button */}
      <TouchableOpacity 
        style={styles.fab}
        onPress={handleAddTransaction}
      >
        <Ionicons name="add" size={32} color="white" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 80, // Add padding for FAB
  },
  filterContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    paddingVertical: 16,
    backgroundColor: '#0f172a',
  },
  filterButton: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
    marginHorizontal: 4,
    backgroundColor: '#1e293b',
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
  monthCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    backgroundColor: '#1e293b',
    borderRadius: 16,
    marginBottom: 16,
  },
  monthName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: 'white',
    width: 80,
  },
  progressBarContainer: {
    flex: 1,
    height: 8,
    backgroundColor: '#334155',
    borderRadius: 4,
    marginHorizontal: 16,
  },
  progressBar: {
    height: 8,
    backgroundColor: '#f59e0b',
    borderRadius: 4,
  },
  monthAmount: {
    fontSize: 18,
    fontWeight: 'bold',
    color: 'white',
    textAlign: 'right',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#0ea5e9',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
  },
});