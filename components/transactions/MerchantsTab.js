import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import Svg, { Circle, Path } from 'react-native-svg';

// Sample merchant data
const merchantData = [
  {
    id: '1',
    name: 'Rogers',
    icon: 'radio-outline',
    iconBgColor: '#dc2626',
    amount: 45.00,
    percentage: 50.0,
    indicatorColor: '#dc2626',
  },
  {
    id: '2',
    name: 'Other',
    icon: 'storefront-outline',
    iconBgColor: '#9ca3af',
    amount: 45.00,
    percentage: 50.0,
    indicatorColor: '#9ca3af',
  }
];

export default function MerchantsTab() {
  const navigation = useNavigation();
  const [currentMonth, setCurrentMonth] = useState('May');
  
  const handleAddTransaction = () => {
    navigation.navigate('AddTransaction');
  };

  const handlePreviousMonth = () => {
    // Logic to go to previous month
    console.log('Previous month');
  };

  const handleNextMonth = () => {
    // Logic to go to next month
    console.log('Next month');
  };

  // Calculate total amount for the donut chart
  const totalAmount = merchantData.reduce((sum, merchant) => sum + merchant.amount, 0);

  const renderHeader = () => (
    <>
      {/* Month Selection */}
      <View style={styles.monthSelector}>
        <TouchableOpacity onPress={handlePreviousMonth}>
          <Ionicons name="chevron-back" size={24} color="#94a3b8" />
        </TouchableOpacity>
        <Text style={styles.monthText}>{currentMonth}</Text>
        <TouchableOpacity onPress={handleNextMonth}>
          <Ionicons name="chevron-forward" size={24} color="#94a3b8" />
        </TouchableOpacity>
      </View>

      {/* Donut Chart */}
      <View style={styles.chartContainer}>
        <View style={styles.donutChartContainer}>
          <Svg height="240" width="240" viewBox="0 0 100 100">
            {/* First half of the donut (Rogers - Red) */}
            <Circle
              cx="50"
              cy="50"
              r="40"
              stroke="#dc2626"
              strokeWidth="20"
              fill="transparent"
              strokeDasharray="125.6 251.2"
              strokeDashoffset="0"
            />
            {/* Second half of the donut (Other - Gray) */}
            <Circle
              cx="50"
              cy="50"
              r="40"
              stroke="#9ca3af"
              strokeWidth="20"
              fill="transparent"
              strokeDasharray="125.6 251.2"
              strokeDashoffset="-125.6"
            />
            {/* Inner circle */}
            <Circle
              cx="50"
              cy="50"
              r="30"
              stroke="#1e293b"
              strokeWidth="1"
              fill="#0f172a"
            />
          </Svg>
          <View style={styles.donutCenterText}>
            <Text style={styles.donutLabel}>Total</Text>
            <Text style={styles.donutAmount}>${totalAmount}</Text>
          </View>
        </View>
      </View>
    </>
  );

  const renderMerchantItem = ({ item }) => (
    <View style={styles.merchantItem}>
      <View style={[styles.merchantIcon, { backgroundColor: item.iconBgColor }]}>
        <Ionicons name={item.icon} size={24} color="white" />
      </View>
      <View style={styles.merchantInfo}>
        <Text style={styles.merchantName}>{item.name}</Text>
        <Text style={styles.merchantPercentage}>{item.percentage.toFixed(1)} %</Text>
      </View>
      <Text style={styles.merchantAmount}>${item.amount.toFixed(2)}</Text>
      <View style={styles.indicatorContainer}>
        <View 
          style={[
            styles.indicatorBar, 
            { backgroundColor: item.indicatorColor }
          ]} 
        />
      </View>
    </View>
  );

  return (
    <FlatList
      data={merchantData}
      renderItem={renderMerchantItem}
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
  monthSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
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
    padding: 16,
    marginVertical: 16,
    marginHorizontal: 16,
    borderWidth: 1,
    borderColor: '#1e293b',
    borderRadius: 16,
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
  merchantItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: '#1e293b',
  },
  merchantIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  merchantInfo: {
    flex: 1,
  },
  merchantName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
    marginBottom: 4,
  },
  merchantPercentage: {
    fontSize: 14,
    color: '#94a3b8',
  },
  merchantAmount: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
    marginRight: 16,
  },
  indicatorContainer: {
    width: 80,
    height: 4,
    backgroundColor: '#1e293b',
    borderRadius: 2,
  },
  indicatorBar: {
    height: 4,
    width: '100%',
    borderRadius: 2,
  },
});